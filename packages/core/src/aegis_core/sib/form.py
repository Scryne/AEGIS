"""ŞİB formunun yapısı ve doğrulama kuralları (saf; veritabanı bilmez) — E2.2, ADR-0011.

Form bölümleri rehberin §4.2 sırasıyla A–G'dir (SMMM formunda hesap bölümü yoktur). Biçim
doğrulaması Pydantic'tedir (yanlış türde alan kaydedilmez); **içerik kuralları** ``denetle``
fonksiyonundadır ve iki sınıf üretir:

- ``hatalar`` — rehberin açıkça "zorunlu", "en az/en fazla", "kullanılacaktır" dediği kurallar.
  Hata varken taslak kaydedilir ama **dışa aktarılamaz**.
- ``uyarilar`` — rehberin "gerekmektedir/belirtilmelidir" diye nitelediği ama MASAK Online'ın
  reddedip etmediği teyit edilemeyen eksikler. Dışa aktarmayı engellemez, ekranda görünür.

Otomatik iskelet metin rehberin "sürekli benzer metin … yer verilmemesi ve her şüpheli işlem
bildirimine ilişkin makul ve özgün açıklama" şartı yüzünden bir hatadır: iskelet olduğu gibi
ya da doldurulmamış yer tutucularla dışa aktarılamaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aegis_core.sib.kodlar import (
    ACIKLAMA_EN_AZ,
    ACIKLAMA_EN_COK,
    KATEGORI_ZORUNLU_SK,
    SK_EN_AZ,
    SK_EN_COK,
    SK_KODLARI,
)

YER_TUTUCU = "[…]"
# İskeletin ilk satırı: kullanıcıya metnin bir başlangıç olduğunu söyler; dışa aktarılan
# açıklamada kalmamalıdır.
YONERGE = (
    "Bu metin AEGIS dosyasındaki kayıtlardan üretilmiş bir başlangıçtır; MASAK her bildirim "
    "için özgün açıklama ister. Kendi değerlendirmenizle yeniden yazın, yer tutucuları "
    "doldurun ve bu satırı silin."
)
_YER_TUTUCU_DESENI = re.compile(r"\[…\]|\[\.\.\.\]")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Yukumlu(_Model):
    """(A) Formu düzenleyen yükümlü."""

    ad_unvan: str = ""
    kimlik_no: str = ""  # TCKN / VKN / YKN
    temsilci_ad_soyad: str = ""
    temsilci_kimlik_no: str = ""


class Bildirim(_Model):
    """(B) Bildirime ilişkin bilgiler. Yükümlü referans no sistem tarafından atanır."""

    tur: Literal["yeni", "ek"] = "yeni"
    onceki_referans_no: str = ""
    kategori: Literal["aklama", "teror", "kis"] | None = None
    teror_orgut_turu: Literal["bolucu", "dini_istismar", "asiri_sol"] | None = None
    aciliyet: Literal["normal", "ivedi", "cok_ivedi", "erteleme_talepli"] = "normal"


class KimlikBelgesi(_Model):
    tur: Literal[
        "nufus_cuzdani",
        "tc_kimlik_karti",
        "surucu_belgesi",
        "yeni_surucu_belgesi",
        "pasaport",
        "ikamet_izni",
        "diger",
    ]
    numara: str = ""
    gecerlilik: date | None = None


class GercekKisi(_Model):
    """(C) Şüpheli işlemle ilgili gerçek kişi — kişi başına tekrarlanır."""

    baglanti: (
        Literal["kendisi_adina", "baskasi_adina", "adina_yapilan", "gercek_faydalanici", "dolayli"]
        | None
    ) = None
    baglanti_aciklamasi: str = ""  # "Dolaylı Olarak İlgili" için ilişkinin mahiyeti
    kimlik_sahte: bool = False
    ad: str = ""
    soyad: str = ""
    kimlik_belgeleri: list[KimlikBelgesi] = Field(default_factory=list)
    tckn: str = ""
    vkn: str = ""
    yabanci_kimlik_veya_pasaport: str = ""
    uyruk: str = ""
    anne_adi: str = ""
    baba_adi: str = ""
    adres: str = ""
    dogum_tarihi: date | None = None
    dogum_yeri: str = ""
    telefon: str = ""
    eposta: str = ""
    is_meslek: str = ""
    ek_bilgi: str = ""
    kaynak_varlik_id: str | None = None  # AEGIS kütüğündeki kaynak kayıt (iz için)


class TuzelKisi(_Model):
    """(D) Şüpheli işlemle ilgili tüzel/diğer kişi — kişilik başına tekrarlanır."""

    baglanti: Literal["adina_yapilan", "dolayli"] | None = None
    baglanti_aciklamasi: str = ""
    belge_sahte: bool = False
    kurulus_nevi: (
        Literal[
            "ticaret_sicili",
            "yurt_disi",
            "tuzel_kisiligi_olmayan",
            "guven_sozlesmesi",
            "dernek",
            "vakif",
            "siyasi_parti",
            "sendika",
        ]
        | None
    ) = None
    unvan: str = ""
    isletme_adi: str = ""
    vkn: str = ""
    sicil_no: str = ""  # MERSİS biliniyorsa MERSİS no
    kurulus_ulkesi: str = ""
    kurulus_yeri: str = ""
    kurulus_tarihi: date | None = None
    adres: str = ""
    faaliyet_konusu: str = ""
    telefon: str = ""
    eposta: str = ""
    web_sitesi: str = ""
    ek_bilgi: str = ""
    kaynak_varlik_id: str | None = None


class SupheliIslem(_Model):
    """(E) Parasal tutarlı şüpheli işlem — farklı mahiyette işlemler için tekrarlanabilir."""

    durum: Literal["tesebbus", "gerceklesmis"] | None = None
    cesit: Literal["tek", "coklu"] | None = None
    tarih: date | None = None
    bitis_tarihi: date | None = None  # çoklu işlemde aralığın sonu
    para_birimi: str = "TRY"
    tutar: Decimal | None = None
    tutar_tl: Decimal | None = None
    ulke: str = ""
    il: str = ""
    ilce: str = ""
    aciklama: str = ""


class SibFormu(_Model):
    yukumlu: Yukumlu = Field(default_factory=Yukumlu)
    bildirim: Bildirim = Field(default_factory=Bildirim)
    gercek_kisiler: list[GercekKisi] = Field(default_factory=list)
    tuzel_kisiler: list[TuzelKisi] = Field(default_factory=list)
    islemler: list[SupheliIslem] = Field(default_factory=list)
    sk_kodlari: list[str] = Field(default_factory=list)
    aciklama: str = ""


class Bulgu(_Model):
    alan: str
    mesaj: str


class Denetim(_Model):
    hatalar: list[Bulgu]
    uyarilar: list[Bulgu]

    @property
    def disa_aktarilabilir(self) -> bool:
        return not self.hatalar


def metin_ozeti(metin: str) -> str:
    """Boşluk farkını yok sayan özet (iskeletin değiştirilip değiştirilmediğini anlamak için)."""
    return hashlib.sha256(" ".join(metin.split()).encode("utf-8")).hexdigest()


def tckn_gecerli(no: str) -> bool:
    if not re.fullmatch(r"[1-9]\d{10}", no):
        return False
    h = [int(c) for c in no]
    onuncu = ((h[0] + h[2] + h[4] + h[6] + h[8]) * 7 - (h[1] + h[3] + h[5] + h[7])) % 10
    return h[9] == onuncu and h[10] == sum(h[:10]) % 10


def denetle(form: SibFormu, *, iskelet_ozeti: str | None = None) -> Denetim:
    """Rehberin içerik kurallarını uygular. Saf fonksiyon: aynı girdi, aynı sonuç."""
    hatalar: list[Bulgu] = []
    uyarilar: list[Bulgu] = []

    def hata(alan: str, mesaj: str) -> None:
        hatalar.append(Bulgu(alan=alan, mesaj=mesaj))

    def uyari(alan: str, mesaj: str) -> None:
        uyarilar.append(Bulgu(alan=alan, mesaj=mesaj))

    # (A)
    if not form.yukumlu.ad_unvan:
        hata("yukumlu.ad_unvan", "Yükümlünün adı soyadı veya unvanı gerekli (A).")
    if not form.yukumlu.kimlik_no:
        hata("yukumlu.kimlik_no", "Yükümlünün TCKN/VKN/YKN bilgisi gerekli (A).")

    # (B)
    b = form.bildirim
    if b.kategori is None:
        hata("bildirim.kategori", "Bildirim kategorisi seçilmeli (B).")
    if b.kategori == "teror" and b.teror_orgut_turu is None:
        hata(
            "bildirim.teror_orgut_turu",
            "Terörizmin finansmanı seçildiğinde terör örgütü türü seçilmeli (B).",
        )
    if b.kategori != "teror" and b.teror_orgut_turu is not None:
        hata(
            "bildirim.teror_orgut_turu",
            "Terör örgütü türü yalnız terörizmin finansmanında seçilir.",
        )
    if b.tur == "ek" and not b.onceki_referans_no:
        hata(
            "bildirim.onceki_referans_no",
            "Ek bildirimde önceki bildirimin yerel referans numarası zorunludur (B).",
        )
    if b.aciliyet == "erteleme_talepli":
        uyari(
            "bildirim.aciliyet",
            "Erteleme talebi salt şüpheden öte belge veya ciddi emare gerektirir; açıklamada "
            "gösterin (rehber §3).",
        )

    # (C) / (D)
    if not form.gercek_kisiler and not form.tuzel_kisiler:
        hata("kisiler", "En az bir gerçek ya da tüzel kişi bilgisi gerekli (C/D).")
    for i, k in enumerate(form.gercek_kisiler):
        alan = f"gercek_kisiler[{i}]"
        if k.baglanti is None:
            hata(f"{alan}.baglanti", "İşlemle olan bağlantısı seçilmeli (C).")
        if k.baglanti == "dolayli" and not k.baglanti_aciklamasi:
            hata(
                f"{alan}.baglanti_aciklamasi", "Dolaylı ilgide ilişkinin mahiyeti açıklanmalı (C)."
            )
        if not k.ad or not k.soyad:
            hata(f"{alan}.ad", "Adı ve soyadı kısaltmasız yazılmalı (C).")
        if k.tckn and not tckn_gecerli(k.tckn):
            uyari(
                f"{alan}.tckn",
                "T.C. kimlik numarası sağlama kuralına uymuyor; kaynağını kontrol edin.",
            )
        if not (k.tckn or k.vkn or k.yabanci_kimlik_veya_pasaport):
            uyari(f"{alan}.tckn", "Kimlik numarası (TCKN, VKN ya da yabancı kimlik/pasaport) yok.")
        if not k.adres:
            uyari(f"{alan}.adres", "Adres (ilçe-il-posta kodu) belirtilmeli (C).")
    for i, t in enumerate(form.tuzel_kisiler):
        alan = f"tuzel_kisiler[{i}]"
        if t.baglanti is None:
            hata(f"{alan}.baglanti", "İşlemle olan bağlantısı seçilmeli (D).")
        if t.baglanti == "dolayli" and not t.baglanti_aciklamasi:
            hata(
                f"{alan}.baglanti_aciklamasi", "Dolaylı ilgide ilişkinin mahiyeti açıklanmalı (D)."
            )
        if not t.unvan:
            hata(f"{alan}.unvan", "Unvan, firma nev'i dahil açık olarak yazılmalı (D).")
        if t.kurulus_nevi is None:
            hata(f"{alan}.kurulus_nevi", "Kuruluş nev'i seçilmeli (D).")
        if t.vkn and not re.fullmatch(r"\d{10}", t.vkn):
            uyari(f"{alan}.vkn", "Vergi kimlik numarası 10 haneli olmalı (D).")

    # (E)
    for i, s in enumerate(form.islemler):
        alan = f"islemler[{i}]"
        if s.durum is None or s.cesit is None:
            hata(f"{alan}.durum", "İşlem durumu ve işlem çeşidi seçilmeli (E).")
        if s.durum == "tesebbus" and s.cesit == "coklu":
            hata(f"{alan}.cesit", "Teşebbüs aşamasındaki işlem her zaman tek işlemdir (E).")
        if s.tarih is None:
            hata(f"{alan}.tarih", "İşlem tarihi gerekli (E).")
        if s.cesit == "coklu" and s.bitis_tarihi is None:
            hata(f"{alan}.bitis_tarihi", "Çoklu işlemde başlangıç ve bitiş tarihi gerekli (E).")
        if s.tarih and s.bitis_tarihi and s.bitis_tarihi < s.tarih:
            hata(f"{alan}.bitis_tarihi", "Bitiş tarihi başlangıçtan önce olamaz (E).")
        if s.tutar is None or s.tutar <= 0:
            hata(
                f"{alan}.tutar",
                "İşlem tutarı gerekli (E; parasal tutar yoksa bölüm boş bırakılır).",
            )
        if s.para_birimi.upper() != "TRY" and s.tutar_tl is None:
            uyari(f"{alan}.tutar_tl", "Yabancı para işlemde TL karşılığı belirtilmeli (E).")
        if not s.ulke or not s.il:
            hata(
                f"{alan}.ulke",
                "İşlemin yapıldığı coğrafi konum (ülke, il) gerekli; şube adı yetmez (E).",
            )

    # (F)
    kodlar = form.sk_kodlari
    bilinmeyen = [k for k in kodlar if k not in SK_KODLARI]
    if bilinmeyen:
        hata(
            "sk_kodlari", f"Şüphe kategorileri tablosunda olmayan kod: {', '.join(bilinmeyen)} (F)."
        )
    if len(set(kodlar)) != len(kodlar):
        hata("sk_kodlari", "Aynı şüphe kategorisi iki kez seçilmiş (F).")
    if not SK_EN_AZ <= len(kodlar) <= SK_EN_COK:
        hata(
            "sk_kodlari", f"Şüphe kategorisi en az {SK_EN_AZ}, en fazla {SK_EN_COK} seçilmeli (F)."
        )
    if b.kategori in KATEGORI_ZORUNLU_SK:
        gerekli = KATEGORI_ZORUNLU_SK[b.kategori]
        if not gerekli & set(kodlar):
            hata(
                "sk_kodlari",
                f"Bu bildirim kategorisinde {' ya da '.join(sorted(gerekli))} kullanılmalı (F).",
            )

    # (G)
    uzunluk = len(form.aciklama)
    if uzunluk < ACIKLAMA_EN_AZ:
        hata("aciklama", f"Açıklama en az {ACIKLAMA_EN_AZ} karakter olmalı (şu an {uzunluk}) (G).")
    if uzunluk > ACIKLAMA_EN_COK:
        hata(
            "aciklama",
            f"Açıklama en fazla {ACIKLAMA_EN_COK:,} karakter olabilir (G).".replace(",", "."),
        )
    if _YER_TUTUCU_DESENI.search(form.aciklama):
        hata("aciklama", f"Açıklamada doldurulmamış yer tutucu ({YER_TUTUCU}) var (G).")
    if YONERGE in form.aciklama:
        hata("aciklama", "İskeletin yönerge satırı açıklamada duruyor; silin (G).")
    if iskelet_ozeti is not None and metin_ozeti(form.aciklama) == iskelet_ozeti:
        hata(
            "aciklama",
            "Açıklama otomatik iskeletle aynı; rehber her bildirim için özgün açıklama ister (G).",
        )
    return Denetim(hatalar=hatalar, uyarilar=uyarilar)
