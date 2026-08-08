"""Türkçe ad normalizasyonu testleri (E1.3).

Bu modül taramanın doğruluk temelidir; testler bilinçli olarak yoğundur. Ölçüt: aynı
gerçek varlığın farklı yazımları **aynı** kanonik anahtara inmeli, farklı varlıklar
inmemelidir. Yanlış negatif (kaçan eşleşme) bu üründeki tehlikeli hata olduğundan
denklik testleri ağır basar; ayırt etme testleri aşırı temizliğe karşı emniyet kemeridir.
"""

from __future__ import annotations

import pytest

from aegis_core.screening.normalization import (
    SubjectType,
    canonicalize,
    name_variants,
    normalize_name,
    to_ascii,
    turkish_lower,
    turkish_upper,
)

# ── İ/ı: Python'un varsayılan casefold'unun yanlış yaptığı yer ────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ISTANBUL", "ıstanbul"),
        ("İSTANBUL", "istanbul"),
        ("IĞDIR", "ığdır"),
        ("İZMİR", "izmir"),
        ("ILGAZ", "ılgaz"),
        ("Işık", "ışık"),
    ],
)
def test_turkish_lower_i_harfleri(raw: str, expected: str) -> None:
    assert turkish_lower(raw) == expected


def test_python_varsayilan_lower_yanlis_yapar() -> None:
    """Neden özel bir fonksiyon yazdığımızın kanıtı (regresyon koruması)."""
    # Varsayılan lower() "I"yı noktalı "i" yapar (Türkçe'de yanlış)…
    assert "I".lower() == "i"
    assert turkish_lower("I") == "ı"
    # …ve "İ"yi iki kod noktasına ayırır (i + birleşik nokta).
    assert len("İ".lower()) == 2
    assert turkish_lower("İ") == "i"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("istanbul", "İSTANBUL"), ("ışık", "IŞIK"), ("izmir", "İZMİR")],
)
def test_turkish_upper(raw: str, expected: str) -> None:
    assert turkish_upper(raw) == expected


# ── Harf çevirisi (uluslararası listeler ASCII yazar) ────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("şahin", "sahin"),
        ("çağlar", "caglar"),
        ("öztürk", "ozturk"),
        ("gülşen", "gulsen"),
        ("ığdır", "igdir"),
        ("kâzım", "kazim"),
        ("josé", "jose"),
    ],
)
def test_to_ascii(raw: str, expected: str) -> None:
    assert to_ascii(raw) == expected


def test_canonicalize_noktalama_ve_bosluk() -> None:
    # Not: canonicalize harf ÇEVİRİSİ yapmaz, yalnız Türkçe-doğru küçültür —
    # bu yüzden "GHI" → "ghı" (I → ı). ASCII biçim ayrı bir alandır.
    assert canonicalize("  ABC   -  DEF / GHI  ") == "abc def ghı"
    assert canonicalize("A.Ş.") == "a ş"
    assert canonicalize('"Yıldız" & Ortakları') == "yıldız ortakları"


def test_canonicalize_unicode_birlesik_ve_ayrik_ayni_sonuca_iner() -> None:
    """Önceden-birleşik ``ü`` ile ``u`` + iki nokta aynı kanonik biçime inmelidir."""
    precomposed = "Gülşen"
    decomposed = "Gülşen"
    assert canonicalize(precomposed) == canonicalize(decomposed)


# ── Tüzel-kişilik ekleri ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ABC Yapı A.Ş.", "abc yapı"),
        ("ABC Yapı Anonim Şirketi", "abc yapı"),
        ("ABC YAPI AŞ", "abc yapı"),
        ("Yıldız İnşaat San. ve Tic. Ltd. Şti.", "yıldız inşaat"),
        ("Yıldız İnşaat Sanayi ve Ticaret Limited Şirketi", "yıldız inşaat"),
        ("Mavi Deniz Turizm Ticaret A.Ş.", "mavi deniz turizm"),
        ("Kaya Kardeşler Koll. Şti.", "kaya kardeşler"),
        ("Ege İthalat İhracat Ltd. Şti.", "ege"),
        ("Anadolu Tekstil Dış Ticaret A.Ş.", "anadolu tekstil"),
    ],
)
def test_sirket_ekleri_temizlenir(raw: str, expected: str) -> None:
    assert normalize_name(raw, SubjectType.COMPANY).canonical == expected


def test_govde_icindeki_tuzel_ek_de_temizlenir() -> None:
    """ "ABC Lojistik A.Ş. İstanbul Şubesi" ile şubesiz hâli aynı ada inmelidir."""
    with_form = normalize_name("ABC Lojistik A.Ş. İstanbul Şubesi", SubjectType.COMPANY)
    without_form = normalize_name("ABC Lojistik İstanbul Şubesi", SubjectType.COMPANY)
    assert with_form.canonical == without_form.canonical == "abc lojistik istanbul"


def test_ve_baglaci_ayirt_edici_degildir() -> None:
    assert (
        normalize_name("Demir ve Çelik Sanayi A.Ş.", SubjectType.COMPANY).canonical
        == normalize_name("Demir & Çelik Sanayi A.Ş.", SubjectType.COMPANY).canonical
    )


def test_ad_tamamen_bosalmaz() -> None:
    """Yalnız tüzel ekten ibaret bir girdi silinip boş bırakılmamalıdır."""
    result = normalize_name("Sanayi A.Ş.", SubjectType.COMPANY)
    assert not result.is_empty
    assert result.canonical


def test_ticaret_govdede_korunur() -> None:
    """Aşırı temizlik testi: sektör kelimesi sonda değilse ayırt edicidir."""
    assert normalize_name("Ticaret Bankası A.Ş.", SubjectType.COMPANY).canonical == (
        "ticaret bankası"
    )


def test_stripped_alani_neyin_atildigini_soyler() -> None:
    result = normalize_name("Yıldız İnşaat San. ve Tic. Ltd. Şti.", SubjectType.COMPANY)
    assert "ltd şti" in result.stripped
    assert "san ve tic" in result.stripped


# ── Kişi adları ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Dr. Şahin Öztürk", "şahin öztürk"),
        ("Av. Ayşe Yılmaz", "ayşe yılmaz"),
        ("Prof. Dr. Mehmet Kaya", "mehmet kaya"),
        ("Şahin Öztürk", "şahin öztürk"),
    ],
)
def test_kisi_unvanlari_temizlenir(raw: str, expected: str) -> None:
    assert normalize_name(raw, SubjectType.PERSON).canonical == expected


def test_kisi_adinda_tuzel_ek_temizligi_yapilmaz() -> None:
    """ "Sanayi" soyadı olabilir; kişi kuralında sektör kelimesi atılmaz."""
    assert normalize_name("Ahmet Sanayi", SubjectType.PERSON).canonical == "ahmet sanayi"


def test_sort_key_kelime_sirasindan_bagimsizdir() -> None:
    duz = normalize_name("Ahmet Yılmaz", SubjectType.PERSON)
    ters = normalize_name("YILMAZ, Ahmet", SubjectType.PERSON)
    assert duz.sort_key == ters.sort_key
    # Ama kanonik biçim sırayı korur (kanıt/gösterim için).
    assert duz.canonical != ters.canonical


# ── Ayırt etme (aşırı temizliğe karşı emniyet kemeri) ────────────────────────


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Yıldız İnşaat", "Yıldız Gıda"),
        ("Ahmet Yılmaz", "Ahmet Yılmazer"),
        ("Kaya Holding", "Kaya Tekstil"),
        ("Demir Çelik", "Demir Çelikkaya"),
    ],
)
def test_farkli_varliklar_ayni_anahtara_inmez(first: str, second: str) -> None:
    assert normalize_name(first).sort_key != normalize_name(second).sort_key


# ── Varyant üretimi (motora gönderilen ad kümesi) ────────────────────────────


def test_name_variants_kanonik_ascii_ve_ham_hepsini_kapsar() -> None:
    variants = name_variants(normalize_name("Şahin Öztürk", SubjectType.PERSON))
    assert "şahin öztürk" in variants
    assert "sahin ozturk" in variants
    assert "Şahin Öztürk" in variants


def test_name_variants_tekrarlari_eler() -> None:
    """ASCII'si kanonikle aynı olan adda varyant çoğalmamalıdır."""
    variants = name_variants(normalize_name("abc", SubjectType.COMPANY))
    assert variants == ("abc",)


def test_bos_girdi_bos_kanonik_uretir() -> None:
    result = normalize_name("   ...   ", SubjectType.COMPANY)
    assert result.is_empty
