"""ŞİB taslağını düzenlenebilir Word belgesine çevirir (E2.2, ADR-0011).

Belge MASAK Online'daki formun bölüm sırasını (A–G) ve alan adlarını rehberdeki yazımıyla
izler: uyum görevlisi değerleri ekrana birebir taşıyabilsin. Seçmeli alanlar kodla değil
rehberdeki etiketle yazılır ("Gerçek Faydalanıcı", "SK-11 Vergi kaçakçılığı ve vergi kaçırma").

Her sayfanın üst ve alt bilgisinde gizlilik ibaresi vardır: bildirimde bulunulduğu, işleme
taraf olanlar dahil kimseye açıklanamaz (5549 s.K. m.4/2) — belge yazıcıda unutulsa bile ne
olduğu belli olmalı.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor

from aegis_core.reports import labels
from aegis_core.sib.form import SibFormu
from aegis_core.sib.kodlar import (
    ACILIYET,
    BILDIRIM_TURU,
    GERCEK_BAGLANTI,
    ISLEM_CESIDI,
    ISLEM_DURUMU,
    KATEGORILER,
    KIMLIK_BELGELERI,
    KURULUS_NEVI,
    REHBER,
    SK_KODLARI,
    TEROR_ORGUT_TURLERI,
    TUZEL_BAGLANTI,
)

GIZLILIK = (
    "GİZLİDİR — 5549 sayılı Kanun m.4/2: şüpheli işlem bildiriminde bulunulduğu, denetim "
    "elemanları ve yargılama sırasında mahkemeler dışında, işleme taraf olanlar dahil hiç "
    "kimseye açıklanamaz."
)
SORUMLULUK = (
    "Bu belge MASAK Online'a giriş için hazırlanmış bir TASLAKTIR. Resmî bildirim, yükümlünün "
    "MASAK Online üzerinden yaptığı bildirimdir ve sorumluluğu yükümlüye aittir. Alan yapısı: "
    f"{REHBER['kod']} ({REHBER['tarih']})."
)
_KIRMIZI = RGBColor(0xB4, 0x23, 0x18)


def _deger(v: Any, sozluk: dict[str, str] | None = None) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "Evet" if v else "Hayır"
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")  # rehber: "gg/aa/yyyy"
    if isinstance(v, Decimal):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if sozluk is not None:
        return sozluk.get(str(v), str(v))
    return str(v)


def _tablo(belge: Any, satirlar: Iterable[tuple[str, str]]) -> None:
    satirlar = list(satirlar)
    tablo = belge.add_table(rows=0, cols=2)
    tablo.style = "Table Grid"
    for etiket, deger in satirlar:
        hucreler = tablo.add_row().cells
        hucreler[0].text = ""
        hucreler[0].paragraphs[0].add_run(etiket).bold = True
        hucreler[1].text = deger
    belge.add_paragraph()


def render_docx(form: SibFormu, referans_no: str, uretim: datetime) -> bytes:
    belge = DocxDocument()
    belge.styles["Normal"].font.size = Pt(10)
    for bolum in belge.sections:
        bolum.header.paragraphs[0].text = f"GİZLİ · ŞİB TASLAĞI · {referans_no}"
        bolum.footer.paragraphs[0].text = GIZLILIK

    belge.add_heading("Şüpheli İşlem Bildirimi — Taslak", level=0)
    uyari = belge.add_paragraph()
    run = uyari.add_run(SORUMLULUK)
    run.bold = True
    run.font.color.rgb = _KIRMIZI
    belge.add_paragraph(
        f"Yükümlü referans no: {referans_no} · Hazırlanma: {labels.format_datetime(uretim)}"
    )

    y = form.yukumlu
    belge.add_heading("(A) Formu Düzenleyen Yükümlü Bilgileri", level=1)
    _tablo(
        belge,
        [
            ("Yükümlünün Ad Soyad veya Unvanı", _deger(y.ad_unvan)),
            ("Yükümlünün TCKN/VKN/YKN bilgisi", _deger(y.kimlik_no)),
            ("Bildirimde Bulunan Temsilcinin Adı ve Soyadı", _deger(y.temsilci_ad_soyad)),
            ("Bildirimde Bulunan Temsilcinin TCKN veya YKN bilgisi", _deger(y.temsilci_kimlik_no)),
        ],
    )

    b = form.bildirim
    belge.add_heading("(B) Bildirime İlişkin Bilgiler", level=1)
    satirlar = [
        ("Yükümlü Referans No.", referans_no),
        ("Yeni veya Ek", _deger(b.tur, BILDIRIM_TURU)),
    ]
    if b.tur == "ek":
        satirlar.append(("Ek İse Önceki Bildirim Referans No.", _deger(b.onceki_referans_no)))
    satirlar.append(("Bildirim Kategorisi", _deger(b.kategori, KATEGORILER)))
    if b.kategori == "teror":
        satirlar.append(("Terör Örgütü", _deger(b.teror_orgut_turu, TEROR_ORGUT_TURLERI)))
    satirlar.append(("Bildirimin Aciliyeti", _deger(b.aciliyet, ACILIYET)))
    _tablo(belge, satirlar)

    belge.add_heading("(C) Şüpheli İşlem ile İlgili Gerçek Kişi Bilgileri", level=1)
    if not form.gercek_kisiler:
        belge.add_paragraph("Bu bölümde kişi yok.")
    for i, k in enumerate(form.gercek_kisiler, start=1):
        belge.add_heading(f"Gerçek kişi {i}", level=2)
        belgeler = "; ".join(
            f"{KIMLIK_BELGELERI[kb.tur]}: {kb.numara}"
            + (f" / {_deger(kb.gecerlilik)}" if kb.gecerlilik else "")
            for kb in k.kimlik_belgeleri
        )
        _tablo(
            belge,
            [
                ("İşlem ile Olan Bağlantısı", _deger(k.baglanti, GERCEK_BAGLANTI)),
                *([("İlişkinin Mahiyeti", k.baglanti_aciklamasi)] if k.baglanti_aciklamasi else []),
                ("Kimliği Sahte mi?", _deger(k.kimlik_sahte)),
                ("Adı", _deger(k.ad)),
                ("Soyadı", _deger(k.soyad)),
                ("Kimlik Belgelerine Dair Bilgiler", belgeler or "—"),
                ("T.C. Kimlik No.", _deger(k.tckn)),
                ("Vergi Kimlik No.", _deger(k.vkn)),
                ("Yabancı Kimlik No/Pasaport No", _deger(k.yabanci_kimlik_veya_pasaport)),
                ("Uyruğu", _deger(k.uyruk)),
                ("Anne Adı", _deger(k.anne_adi)),
                ("Baba Adı", _deger(k.baba_adi)),
                ("Adres", _deger(k.adres)),
                ("Doğum Tarihi", _deger(k.dogum_tarihi)),
                ("Doğum Yeri", _deger(k.dogum_yeri)),
                ("Telefon Numarası", _deger(k.telefon)),
                ("Elektronik Posta Adresi", _deger(k.eposta)),
                ("İş ve Meslek", _deger(k.is_meslek)),
                ("Varsa Ek Bilgi", _deger(k.ek_bilgi)),
            ],
        )

    belge.add_heading("(D) Şüpheli İşlem ile İlgili Tüzel/Diğer Kişilere Ait Bilgiler", level=1)
    if not form.tuzel_kisiler:
        belge.add_paragraph("Bu bölümde kişilik yok.")
    for i, t in enumerate(form.tuzel_kisiler, start=1):
        belge.add_heading(f"Tüzel/diğer kişi {i}", level=2)
        _tablo(
            belge,
            [
                ("İşlem ile Olan Bağlantısı", _deger(t.baglanti, TUZEL_BAGLANTI)),
                *([("İlişkinin Mahiyeti", t.baglanti_aciklamasi)] if t.baglanti_aciklamasi else []),
                ("Kimliğe esas belge sahte mi?", _deger(t.belge_sahte)),
                ("Kuruluş Nev'i", _deger(t.kurulus_nevi, KURULUS_NEVI)),
                ("Unvan", _deger(t.unvan)),
                ("İşletme Adı", _deger(t.isletme_adi)),
                ("Vergi Kimlik No.", _deger(t.vkn)),
                ("Sicil Numarası", _deger(t.sicil_no)),
                ("Kurulduğu Ülke", _deger(t.kurulus_ulkesi)),
                ("Kurulduğu Yer", _deger(t.kurulus_yeri)),
                ("Kuruluş Tarihi", _deger(t.kurulus_tarihi)),
                ("Adresi", _deger(t.adres)),
                ("Faaliyet konusu", _deger(t.faaliyet_konusu)),
                ("Telefon Numarası", _deger(t.telefon)),
                ("Elektronik Posta Adresi", _deger(t.eposta)),
                ("Web Sitesi", _deger(t.web_sitesi)),
                ("Varsa Ek Bilgi", _deger(t.ek_bilgi)),
            ],
        )

    belge.add_heading("(E) Şüpheli İşlem Bilgileri", level=1)
    if not form.islemler:
        belge.add_paragraph(
            "Parasal tutar içeren şüpheli işlem yok; şüpheye gerekçe olan hususlar açıklama "
            "bölümündedir (rehber §4.2.5)."
        )
    for i, s in enumerate(form.islemler, start=1):
        belge.add_heading(f"Şüpheli işlem {i}", level=2)
        tarih = _deger(s.tarih) + (f" – {_deger(s.bitis_tarihi)}" if s.cesit == "coklu" else "")
        _tablo(
            belge,
            [
                ("İşlem Durumu", _deger(s.durum, ISLEM_DURUMU)),
                ("İşlem Çeşidi", _deger(s.cesit, ISLEM_CESIDI)),
                ("İşlem Tarihi", tarih),
                ("Para Birimi", _deger(s.para_birimi)),
                ("İşlem Tutarı", _deger(s.tutar)),
                (
                    "İşlem Tutarı (TP)",
                    _deger(s.tutar_tl if s.para_birimi.upper() != "TRY" else s.tutar),
                ),
                (
                    "İşlemin Yapıldığı Yer",
                    " / ".join(p for p in (s.ulke, s.il, s.ilce) if p) or "—",
                ),
                ("İşlem Açıklaması", _deger(s.aciklama)),
            ],
        )

    belge.add_heading("(F) Şüphe Kategorisi", level=1)
    for kod in form.sk_kodlari:
        belge.add_paragraph(f"{kod} {SK_KODLARI.get(kod, '')}", style="List Bullet")

    belge.add_heading("(G) Açıklama", level=1)
    for paragraf in form.aciklama.split("\n"):
        belge.add_paragraph(paragraf)
    belge.add_paragraph(f"({len(form.aciklama):,} karakter)".replace(",", "."))

    tampon = io.BytesIO()
    belge.save(tampon)
    return tampon.getvalue()
