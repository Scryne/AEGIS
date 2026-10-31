"""ŞİB formu içerik kuralları (E2.2) — rehber MSK-RHB-ŞİB-018-1.0 §4.2.

Her kural rehberde yazılı bir cümleye dayanır; testler hem kuralın tetiklendiği hem de geçerli
formun temiz geçtiği durumu sınar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from aegis_core.sib.form import (
    Bildirim,
    GercekKisi,
    SibFormu,
    SupheliIslem,
    TuzelKisi,
    Yukumlu,
    denetle,
    metin_ozeti,
    tckn_gecerli,
)
from aegis_core.sib.kodlar import SK_KODLARI

ACIKLAMA = (
    "Müşteri şirketin 2026 yılı üçüncü çeyrek defterlerinde, faaliyet konusuyla ilgisi "
    "bulunmayan ve tamamı nakit olarak tahsil edildiği beyan edilen danışmanlık gelirleri "
    "tespit edilmiştir. Gelirlerin karşı tarafı olarak gösterilen iki firmanın adreslerinin "
    "aynı olduğu ve ortaklık yapılarında yaptırım listesinde yer alan bir kişinin dolaylı "
    "pay sahibi olduğu görülmüştür. Fonların kaynağı sorulduğunda belge sunulamamıştır."
)


def _gecerli() -> SibFormu:
    return SibFormu(
        yukumlu=Yukumlu(ad_unvan="Örnek SMMM Bürosu", kimlik_no="1234567890"),
        bildirim=Bildirim(kategori="aklama"),
        tuzel_kisiler=[
            TuzelKisi(
                baglanti="adina_yapilan", kurulus_nevi="ticaret_sicili", unvan="Deniz Ticaret A.Ş."
            )
        ],
        gercek_kisiler=[
            GercekKisi(
                baglanti="gercek_faydalanici",
                ad="Ayşe",
                soyad="Yılmaz",
                tckn="10000000146",
                adres="Nilüfer / Bursa 16110",
            )
        ],
        sk_kodlari=["SK-11"],
        aciklama=ACIKLAMA,
    )


def _alanlar(form: SibFormu, **kw: object) -> set[str]:
    return {b.alan for b in denetle(form, **kw).hatalar}  # type: ignore[arg-type]


def test_gecerli_form_hatasiz() -> None:
    d = denetle(_gecerli())
    assert d.hatalar == []
    assert d.disa_aktarilabilir


def test_sk_tablosu_41_kod() -> None:
    assert len(SK_KODLARI) == 41
    assert next(iter(SK_KODLARI)) == "SK-01"
    assert list(SK_KODLARI)[-1] == "SK-41"


@pytest.mark.parametrize(
    ("kodlar", "hatali"),
    [
        ([], True),
        (["SK-11"], False),
        (["SK-11", "SK-17", "SK-14"], False),
        (["SK-01", "SK-02", "SK-03", "SK-04"], True),
        (["SK-99"], True),
        (["SK-11", "SK-11"], True),
    ],
)
def test_sk_en_az_bir_en_fazla_uc(kodlar: list[str], hatali: bool) -> None:
    f = _gecerli()
    f.sk_kodlari = kodlar
    assert ("sk_kodlari" in _alanlar(f)) is hatali


def test_teror_kategorisi_orgut_turu_ve_sk23_35_ister() -> None:
    f = _gecerli()
    f.bildirim.kategori = "teror"
    alanlar = _alanlar(f)
    assert {"bildirim.teror_orgut_turu", "sk_kodlari"} <= alanlar
    f.bildirim.teror_orgut_turu = "bolucu"
    f.sk_kodlari = ["SK-35"]
    assert _alanlar(f) == set()


def test_kis_kategorisi_sk36_ister() -> None:
    f = _gecerli()
    f.bildirim.kategori = "kis"
    assert "sk_kodlari" in _alanlar(f)
    f.sk_kodlari = ["SK-36"]
    assert _alanlar(f) == set()


def test_ek_bildirim_onceki_referans_ister() -> None:
    f = _gecerli()
    f.bildirim.tur = "ek"
    assert "bildirim.onceki_referans_no" in _alanlar(f)
    f.bildirim.onceki_referans_no = "SIB-2026-0001"
    assert _alanlar(f) == set()


def test_aciklama_300_ile_50000_arasi_ve_yer_tutucusuz() -> None:
    f = _gecerli()
    f.aciklama = "x" * 299
    assert "aciklama" in _alanlar(f)
    f.aciklama = "x" * 300
    assert "aciklama" not in _alanlar(f)
    f.aciklama = "x" * 50_001
    assert "aciklama" in _alanlar(f)
    f.aciklama = ACIKLAMA + " Yapılan araştırma: […]"
    assert "aciklama" in _alanlar(f)


def test_iskelet_degistirilmeden_disa_aktarilamaz() -> None:
    f = _gecerli()
    ozet = metin_ozeti(f.aciklama)
    assert "aciklama" in _alanlar(f, iskelet_ozeti=ozet)
    # Yalnız boşluk farkı "değişiklik" sayılmaz.
    f.aciklama = "  " + f.aciklama.replace(" ", "  ")
    assert "aciklama" in _alanlar(f, iskelet_ozeti=ozet)
    f.aciklama = ACIKLAMA + " Müşteriyle yapılan görüşme tutanağı dosyadadır."
    assert "aciklama" not in _alanlar(f, iskelet_ozeti=ozet)


def test_kisi_bolumu_kurallari() -> None:
    f = _gecerli()
    f.gercek_kisiler[0].baglanti = "dolayli"
    assert "gercek_kisiler[0].baglanti_aciklamasi" in _alanlar(f)
    f.gercek_kisiler = []
    f.tuzel_kisiler = []
    assert "kisiler" in _alanlar(f)
    f.tuzel_kisiler = [TuzelKisi(baglanti="adina_yapilan", unvan="X")]
    assert "tuzel_kisiler[0].kurulus_nevi" in _alanlar(f)


def test_islem_bolumu_kurallari() -> None:
    f = _gecerli()
    f.islemler = [
        SupheliIslem(
            durum="tesebbus",
            cesit="coklu",
            tarih=date(2026, 9, 1),
            tutar=Decimal(1),
            ulke="Türkiye",
            il="Bursa",
        )
    ]
    assert "islemler[0].cesit" in _alanlar(f)
    f.islemler[0].durum = "gerceklesmis"
    assert "islemler[0].bitis_tarihi" in _alanlar(f)
    f.islemler[0].bitis_tarihi = date(2026, 9, 30)
    assert _alanlar(f) == set()
    f.islemler[0].il = ""
    assert "islemler[0].ulke" in _alanlar(f)


def test_tckn_saglama_uyari_olarak() -> None:
    assert tckn_gecerli("10000000146")
    assert not tckn_gecerli("10000000147")
    f = _gecerli()
    f.gercek_kisiler[0].tckn = "10000000147"
    d = denetle(f)
    assert d.disa_aktarilabilir  # kaydedilene saygı: uyarı, engel değil (CLAUDE.md kütük kuralı)
    assert any(u.alan == "gercek_kisiler[0].tckn" for u in d.uyarilar)


def test_bilinmeyen_alan_reddedilir() -> None:
    with pytest.raises(ValidationError, match="hesaplar"):
        SibFormu.model_validate({"hesaplar": []})
