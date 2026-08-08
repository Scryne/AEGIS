"""Kimlik numarası doğrulama testleri (E1.4).

TCKN algoritması **bilinen doğrulama değeriyle** sabitlenir: ``10000000146`` resmî
örneklerde geçen geçerli bir numaradır. Bu test, algoritmanın elle yeniden yazılması
hâlinde kaymasını engeller.

Testlerin ikinci işlevi, doğrulamanın **tavsiye** olduğunu sabitlemektir: fonksiyonlar
bulgu döndürür, kayıt reddetmez.
"""

from __future__ import annotations

import pytest

from aegis_core.entities.identifiers import (
    IdentifierKind,
    check_identifier,
    is_valid_lei,
    is_valid_tckn,
    is_valid_vkn,
    is_well_formed_mersis,
    normalize_digits,
    normalize_lei,
)

# Yaygın olarak yayımlanan geçerli örnek TCKN.
GECERLI_TCKN = "10000000146"


def test_bilinen_gecerli_tckn() -> None:
    """Algoritmanın çapası: bu değer bozulursa doğrulayıcı yanlış yazılmış demektir."""
    assert is_valid_tckn(GECERLI_TCKN) is True


def test_tckn_kontrol_basamagi_bozulursa_reddedilir() -> None:
    bozuk = GECERLI_TCKN[:-1] + ("7" if GECERLI_TCKN[-1] != "7" else "8")
    assert is_valid_tckn(bozuk) is False


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1234567890",  # 10 hane
        "123456789012",  # 12 hane
        "01234567890",  # 0 ile başlıyor
        "abcdefghijk",
    ],
)
def test_bicimsiz_tckn_reddedilir(value: str) -> None:
    assert is_valid_tckn(value) is False


def test_tckn_bicimlendirmeden_bagimsizdir() -> None:
    assert is_valid_tckn("100 000 001 46") is True
    assert is_valid_tckn("10000000-146") is True


def test_vkn_kendi_urettigi_kontrol_basamagiyla_tutarlidir() -> None:
    """VKN algoritması kendi içinde tutarlı olmalı (üret → doğrula).

    Not: bu test algoritmanın resmî spesifikasyona UYGUNLUĞUNU kanıtlamaz, tutarlılığını
    kanıtlar — bu yüzden VKN doğrulaması üründe yalnız uyarı üretir (bkz. modül başlığı).
    """
    govde = "123456789"
    # Doğrulayıcının kabul ettiği kontrol basamağını arayarak bul.
    gecerli = [d for d in range(10) if is_valid_vkn(govde + str(d))]
    assert len(gecerli) == 1, "Tam olarak bir kontrol basamağı geçerli olmalı"
    assert is_valid_vkn(govde + str(gecerli[0])) is True


@pytest.mark.parametrize("value", ["", "12345", "12345678901"])
def test_bicimsiz_vkn_reddedilir(value: str) -> None:
    assert is_valid_vkn(value) is False


def test_mersis_yalniz_bicim_dogrulanir() -> None:
    assert is_well_formed_mersis("0" * 16) is True
    assert is_well_formed_mersis("0" * 15) is False


def test_lei_iso_17442() -> None:
    """GLEIF'in kendi yayımladığı örnek LEI (mod-97-10 kontrolü)."""
    assert is_valid_lei("529900T8BM49AURSDO55") is True


def test_lei_bozulursa_reddedilir() -> None:
    assert is_valid_lei("529900T8BM49AURSDO54") is False
    assert is_valid_lei("KISA") is False


def test_lei_normalizasyonu() -> None:
    assert normalize_lei("5299-00t8 bm49AURSDO55") == "529900T8BM49AURSDO55"


def test_normalize_digits() -> None:
    assert normalize_digits("123 456-78 90") == "1234567890"


# ── check_identifier: bulgu döndürür, karar vermez ───────────────────────────


def test_check_identifier_gecerli_tckn() -> None:
    result = check_identifier(IdentifierKind.TCKN, "100 000 001 46")
    assert result.normalized == GECERLI_TCKN
    assert result.well_formed is True
    assert result.checksum_ok is True
    assert result.looks_valid is True
    assert result.reason is None


def test_check_identifier_kontrol_basamagi_tutmayan_numarayi_reddetmez() -> None:
    """Kontrol basamağı tutmasa bile bulgu döner — kayıt engellenmez, uyarılır."""
    result = check_identifier(IdentifierKind.TCKN, "12345678901")
    assert result.well_formed is True
    assert result.checksum_ok is False
    assert result.looks_valid is False
    assert result.reason is not None
    assert "kontrol basamağı" in result.reason.lower()
    # Normalize edilmiş değer yine de kullanılabilir durumda:
    assert result.normalized == "12345678901"


def test_check_identifier_mersis_checksum_bilinmez() -> None:
    result = check_identifier(IdentifierKind.MERSIS, "0" * 16)
    assert result.well_formed is True
    assert result.checksum_ok is None
    # Algoritma bilinmiyor diye numara şüpheli sayılmaz.
    assert result.looks_valid is True


def test_check_identifier_bicimsiz_deger() -> None:
    result = check_identifier(IdentifierKind.VKN, "123")
    assert result.well_formed is False
    assert result.looks_valid is False
    assert result.reason is not None


def test_check_identifier_lei() -> None:
    result = check_identifier(IdentifierKind.LEI, "529900t8bm49aursdo55")
    assert result.normalized == "529900T8BM49AURSDO55"
    assert result.looks_valid is True
