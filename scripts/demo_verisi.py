"""AEGIS demo verisi — bir uyum danışmanlığının üç KYB vakası, gerçek API akışıyla.

Her şey **kurgusaldır** (kurum, kişi, vergi/kimlik numaraları). Tarama, değerlendirme
yente'sine (34 referans varlık, `aegis_eval`) karşı koşar; üretim kataloğu (OpenSanctions +
MASAK) gerekmez. Kişi eşleşmesi bilinçli olarak üretilmez: değerlendirme setindeki yaygın
Türkçe adlar gerçek kişilerle örtüşebilir, demo ekranında hiçbir kişi "yaptırım adayı"
olarak görünmez.

Vakalar:
  1. Kuzey Ambalaj — temiz: yönetici + gerçek faydalanıcı, imza sirküleri PDF'inden çıkarım
     önerileri, eşleşmesiz tarama, PDF dosya raporu.
  2. ABC Yapı — yazım varyantıyla gelen şirket listedeki kayda eşleşir; analist DOĞRULAR.
  3. Mavi Deniz Turizm Ltd. — eşadlı, farklı şirket; analist gerekçeyle REDDEDER.

Kullanım (API + worker + eval yente ayakta; bkz. README "Yerel demo"):

    uv run python scripts/demo_verisi.py [--api http://localhost:8000]

Aynı organizasyonda varlık varsa durur (``--force`` yine girer; kayıtları çoğaltır).
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from aegis_core.entities.identifiers import is_valid_tckn, is_valid_vkn

ORG = {
    "org_name": "Anadolu Uyum Danışmanlık A.Ş.",
    "org_slug": "anadolu-uyum",
    "email": "selin.demir@example.com",
    "password": "AegisDemo-2026",
    "full_name": "Selin Demir",
}


def _vkn(onek: str) -> str:
    """Kontrol basamağı tutan kurgusal VKN (ilk 9 hane verilir)."""
    for son in "0123456789":
        if is_valid_vkn(onek + son):
            return onek + son
    raise ValueError(onek)


def _tckn(ilk9: str) -> str:
    """Kontrol basamakları tutan kurgusal TCKN (ilk 9 hane verilir)."""
    d = [int(c) for c in ilk9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    sonuc = f"{ilk9}{d10}{d11}"
    if not is_valid_tckn(sonuc):
        raise ValueError(sonuc)
    return sonuc


class Istemci:
    def __init__(self, api: str) -> None:
        self.http = httpx.Client(base_url=api, timeout=180)
        self.token = ""

    def istek(self, yontem: str, yol: str, **kw: Any) -> Any:
        r = self.http.request(yontem, yol, headers={"Authorization": f"Bearer {self.token}"}, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{yontem} {yol} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def giris(self) -> None:
        r = self.http.post("/api/v1/auth/register", json=ORG)
        if r.status_code not in (201, 409):
            raise RuntimeError(f"kayıt -> {r.status_code}: {r.text[:200]}")
        r = self.http.post(
            "/api/v1/auth/login", json={"email": ORG["email"], "password": ORG["password"]}
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]


def _varlik(c: Istemci, **alanlar: Any) -> dict[str, Any]:
    return c.istek("POST", "/api/v1/entities", json=alanlar)["entity"]


def _bag(c: Istemci, hedef: str, kaynak: str, tur: str, **alanlar: Any) -> None:
    c.istek(
        "POST",
        f"/api/v1/entities/{hedef}/relationships",
        json={"source_entity_id": kaynak, "rel_type": tur, **alanlar},
    )


def _tr_upper(metin: str) -> str:
    """Türkçe büyük harf: str.upper() "i"yi "I" yapar ("SANAYI", "ŞIRKETI")."""
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _imza_sirkuleri_pdf(unvan: str, yetkililer: list[tuple[str, str, str]]) -> bytes:
    """Gerçek bir imza sirkülerinin metin düzeninde kurgusal PDF (reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    # Türkçe karakter için TTF gerekir; bulunamazsa Helvetica (ç/ğ/ş kaybolur).
    font = "Helvetica"
    for aday in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(aday).exists():
            pdfmetrics.registerFont(TTFont("Govde", aday))
            font = "Govde"
            break
    tampon = io.BytesIO()
    pdf = canvas.Canvas(tampon, pagesize=A4)
    y = 780
    for satir in [
        "İMZA SİRKÜLERİ",
        "",
        _tr_upper(unvan),
        "",
        "Şirketimizi temsil ve ilzama yetkili kişiler aşağıda gösterilmiştir.",
        "",
    ]:
        pdf.setFont(font, 13 if satir == "İMZA SİRKÜLERİ" else 11)
        pdf.drawString(70, y, satir)
        y -= 22
    for ad, tckn, yetki in yetkililer:
        pdf.setFont(font, 11)
        pdf.drawString(70, y, f"{_tr_upper(ad)} - T.C. Kimlik No: {tckn}")
        y -= 18
        pdf.drawString(70, y, yetki)
        y -= 30
    pdf.drawString(70, y - 10, "Ankara 12. Noterliği")
    pdf.drawString(70, y - 30, "Tarih: 14.03.2026")
    pdf.save()
    return tampon.getvalue()


def _tarama(c: Istemci, varlik_id: str) -> dict[str, Any]:
    tarama = c.istek("POST", f"/api/v1/screenings/from-entity/{varlik_id}")
    for _ in range(60):
        if tarama.get("status") in ("completed", "failed"):
            return tarama
        time.sleep(2)
        tarama = c.istek("GET", f"/api/v1/screenings/{tarama['id']}")
    return tarama


def _karar(c: Istemci, tarama: dict[str, Any], karar: str, not_: str) -> int:
    n = 0
    for aday in tarama.get("candidates") or []:
        if aday.get("subject_role") == "self" and aday.get("decision") in (None, "pending"):
            c.istek(
                "POST",
                f"/api/v1/screenings/{tarama['id']}/candidates/{aday['id']}/decision",
                json={"decision": karar, "note": not_},
            )
            n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="AEGIS demo verisi")
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    c = Istemci(args.api)
    c.giris()
    if c.istek("GET", "/api/v1/entities").get("items") and not args.force:
        print("Bu organizasyonda zaten varlık var; --force ile yine de girilir.")
        return 1

    # 1) Kuzey Ambalaj — temiz vaka
    kuzey = _varlik(
        c,
        name="Kuzey Ambalaj Sanayi ve Ticaret A.Ş.",
        schema_type="Company",
        country="tr",
        tax_number=_vkn("583201946"),
        trade_registry_number="412587",
        incorporation_date="2011-04-18",
        address="Sincan OSB, 12. Cadde No: 7, Ankara",
        notes="Oluklu mukavva ambalaj üreticisi. Yeni müşteri kabulü — KYB dosyası.",
    )
    deniz_tc, cem_tc = _tckn("352418907"), _tckn("218736405")
    deniz = _varlik(
        c, name="Deniz Karaca", schema_type="Person", country="tr", national_id=deniz_tc
    )
    cem = _varlik(c, name="Cem Aksoy", schema_type="Person", country="tr", national_id=cem_tc)
    elif_ = _varlik(c, name="Elif Yurtsever", schema_type="Person", country="tr")
    _bag(c, kuzey["id"], deniz["id"], "officer", role_title="Yönetim Kurulu Başkanı")
    _bag(c, kuzey["id"], cem["id"], "ubo", ownership_percent=62.5)
    _bag(c, kuzey["id"], elif_["id"], "shareholder", ownership_percent=37.5)
    pdf = _imza_sirkuleri_pdf(
        "Kuzey Ambalaj Sanayi ve Ticaret Anonim Şirketi",
        [
            ("Deniz Karaca", deniz_tc, "Şirketi münferiden temsil ve ilzama yetkilidir."),
            (
                "Elif Yurtsever",
                _tckn("463920518"),
                "Yönetim Kurulu Üyesi olarak müştereken imza yetkisine sahiptir.",
            ),
        ],
    )
    belge = c.istek(
        "POST",
        "/api/v1/documents",
        files={"file": ("kuzey-ambalaj-imza-sirkuleri.pdf", pdf, "application/pdf")},
        data={"doc_type": "imza_sirkuleri", "entity_id": kuzey["id"]},
    )
    print("  Kuzey Ambalaj: 1 şirket + 3 kişi + imza sirküleri", belge.get("extraction_status"))

    # 2) ABC Yapı — doğrulanan eşleşme
    abc = _varlik(
        c,
        name="ABC Yapı Sanayi A.Ş.",
        schema_type="Company",
        country="tr",
        tax_number=_vkn("104733582"),
        notes="Tedarikçi olarak başvurdu. Unvan yazımı listedeki kayıttan farklı (A.Ş. eki).",
    )
    bora = _varlik(c, name="Bora Tunçer", schema_type="Person", country="tr")
    _bag(c, abc["id"], bora["id"], "officer", role_title="Genel Müdür")

    # 3) Mavi Deniz Turizm Ltd. — eşadlı yanlış pozitif
    mavi = _varlik(
        c,
        name="Mavi Deniz Turizm Ltd. Şti.",
        schema_type="Company",
        country="tr",
        tax_number=_vkn("617254093"),
        address="Bodrum Marina, Muğla",
        notes="Bodrum'da yat kiralama. Listedeki 'Mavi Deniz Turizm' ile eşadlı.",
    )
    nil = _varlik(c, name="Nil Aydemir", schema_type="Person", country="tr")
    _bag(c, mavi["id"], nil["id"], "officer", role_title="Şirket Müdürü")

    # Taramalar + analist kararları
    t_kuzey = _tarama(c, kuzey["id"])
    t_abc = _tarama(c, abc["id"])
    t_mavi = _tarama(c, mavi["id"])
    n_abc = _karar(
        c,
        t_abc,
        "confirmed",
        "Unvan yalnız hukuki ekte farklı; adres ve faaliyet alanı liste kaydıyla örtüşüyor. "
        "İlişki reddedildi, MASAK'a şüpheli işlem bildirimi değerlendirmesine iletildi.",
    )
    n_mavi = _karar(
        c,
        t_mavi,
        "dismissed",
        "Farklı tüzel kişi: vergi no ve kuruluş ili liste kaydıyla uyuşmuyor, liste kaydı "
        "anonim şirket, müşteri limited şirket. Ad benzerliğinden kaynaklı yanlış pozitif.",
    )
    for ad, t in (("Kuzey", t_kuzey), ("ABC", t_abc), ("Mavi Deniz", t_mavi)):
        print(f"  tarama {ad}: {t.get('status')} · aday {t.get('candidate_count')}")
    print(f"  kararlar: ABC doğrulandı {n_abc}, Mavi Deniz reddedildi {n_mavi}")

    # Dosya raporları (PDF)
    for v in (kuzey, abc):
        c.istek(
            "POST", "/api/v1/reports/dossier", json={"entity_id": v["id"], "report_format": "pdf"}
        )
    print("  dosya raporu: 2 (PDF)")
    print(f"\nTamam. Giriş: {ORG['email']} / {ORG['password']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
