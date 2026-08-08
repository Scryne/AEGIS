"""Kimlik numarası normalizasyonu ve kontrol basamağı doğrulaması (E1.4).

Kapsam: **TCKN** (T.C. kimlik no), **VKN** (vergi kimlik no), **MERSİS no**, **LEI**.
İki yerde kullanılır:

1. **Manuel girişte** — kullanıcıya uyarı üretmek için.
2. **Belge çıkarımında** — bir regex'in yakaladığı 10/11 haneli sayının gerçekten bir
   kimlik numarası olduğuna dair kesinlik filtresi. İmza sirkülerinde tarih, sermaye ve
   sicil numaraları da rakam öbeğidir; kontrol basamağı bunları ayıklar.

**Doğrulama TAVSİYEDİR, ENGEL DEĞİLDİR.** ``check_identifier`` bir karar değil, bir
*bulgu* döndürür ve çağıran katmanlar (API, çıkarım) kaydı asla reddetmez — yalnız
işaretler. Gerekçe: bir uyum aracının, kullanıcının elindeki gerçek bir belgede yazan
numarayı kaydetmesini engellemesi kabul edilemez. Kontrol algoritmalarının kendisi de
resmî yayınlardan türetilmiştir ve bir kenar durumda yanılabilir; yanılma maliyeti bu
tasarımda "gereksiz uyarı"dır, "veri girilemedi" değil.

TCKN algoritması bilinen doğrulama değeriyle (``10000000146``) teyit edilmiştir; LEI
ISO 17442 (mod-97-10) standardını uygular. VKN algoritması yaygın uygulamalardan
alınmıştır ve yalnız uyarı üretir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_NON_DIGIT = re.compile(r"\D+")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")

TCKN_LENGTH = 11
VKN_LENGTH = 10
MERSIS_LENGTH = 16
LEI_LENGTH = 20


class IdentifierKind(StrEnum):
    """Desteklenen kimlik numarası türleri."""

    TCKN = "tckn"
    """T.C. kimlik numarası — **kişisel veridir**, şifreli kolonda saklanır (ADR-0005)."""

    VKN = "vkn"
    """Vergi kimlik numarası (tüzel kişi). Şahıs işletmelerinde TCKN ile aynı olabilir."""

    MERSIS = "mersis"
    LEI = "lei"


def normalize_digits(value: str) -> str:
    """Rakam dışındaki her şeyi atar ("123 456-78 90" → "1234567890")."""
    return _NON_DIGIT.sub("", value)


def normalize_lei(value: str) -> str:
    """LEI'yi kanonikleştirir: harf/rakam dışını atar, büyük harfe çevirir."""
    return _NON_ALNUM.sub("", value).upper()


@dataclass(frozen=True)
class IdentifierCheck:
    """Bir kimlik numarasının incelenmesi — **bulgu**, karar değil."""

    kind: IdentifierKind
    normalized: str
    well_formed: bool
    """Uzunluk/biçim beklenene uyuyor mu."""

    checksum_ok: bool | None
    """Kontrol basamağı tuttu mu. ``None`` = bu tür için doğrulanabilir bir algoritma yok."""

    reason: str | None = None

    @property
    def looks_valid(self) -> bool:
        """Biçim doğru ve (varsa) kontrol basamağı tutuyor.

        Çıkarım hattı bunu **güven skoru** olarak kullanır; API yalnız uyarı üretir.
        """
        return self.well_formed and self.checksum_ok is not False


def is_valid_tckn(value: str) -> bool:
    """TCKN kontrol basamaklarını doğrular.

    Kural (11 hane, ilk hane 0 olamaz)::

        d10 = ((d1+d3+d5+d7+d9) * 7 - (d2+d4+d6+d8)) mod 10
        d11 = (d1 + ... + d10) mod 10

    Bilinen doğrulama değeri ``10000000146`` ile teyit edilmiştir (bkz. testler).
    """
    digits = normalize_digits(value)
    if len(digits) != TCKN_LENGTH or digits[0] == "0":
        return False
    numbers = [int(char) for char in digits]
    odd_sum = numbers[0] + numbers[2] + numbers[4] + numbers[6] + numbers[8]
    even_sum = numbers[1] + numbers[3] + numbers[5] + numbers[7]
    if (odd_sum * 7 - even_sum) % 10 != numbers[9]:
        return False
    return sum(numbers[:10]) % 10 == numbers[10]


def is_valid_vkn(value: str) -> bool:
    """VKN (10 hane) kontrol basamağını doğrular.

    Algoritma yaygın açık kaynak uygulamalarından alınmıştır. Yalnız **uyarı** üretmek
    için kullanılır: bir kenar durumda yanılırsa maliyeti gereksiz bir uyarıdır, veri
    kaybı ya da girilememe değil (bkz. modül başlığı).
    """
    digits = normalize_digits(value)
    if len(digits) != VKN_LENGTH:
        return False
    numbers = [int(char) for char in digits]
    total = 0
    for index in range(9):
        tmp = (numbers[index] + (9 - index)) % 10
        if tmp == 0:
            continue
        product = (tmp * (2 ** (9 - index))) % 9
        total += product if product != 0 else 9
    return (10 - (total % 10)) % 10 == numbers[9]


def is_valid_lei(value: str) -> bool:
    """LEI'yi ISO 17442 (ISO 7064 mod-97-10) kontrol basamaklarıyla doğrular.

    20 karakter; harfler sayıya çevrilir (A=10 … Z=35) ve tüm dizinin 97'ye bölümünden
    kalan 1 olmalıdır.
    """
    lei = normalize_lei(value)
    if len(lei) != LEI_LENGTH or not lei.isalnum():
        return False
    converted = ""
    for char in lei:
        converted += char if char.isdigit() else str(ord(char) - 55)
    try:
        return int(converted) % 97 == 1
    except ValueError:  # pragma: no cover - isalnum zaten güvence
        return False


def is_well_formed_mersis(value: str) -> bool:
    """MERSİS numarasının biçimini doğrular (16 hane).

    Kontrol basamağı algoritması kamuya açık ve teyit edilebilir biçimde yayımlanmadığı
    için **yalnız biçim** kontrol edilir; uydurulmuş bir algoritma, gerçek numaraları
    yanlışlıkla reddederdi.
    """
    return len(normalize_digits(value)) == MERSIS_LENGTH


def check_identifier(kind: IdentifierKind | str, value: str) -> IdentifierCheck:
    """Bir kimlik numarasını normalize eder ve inceler (bulgu döndürür, karar vermez)."""
    resolved = IdentifierKind(kind)
    # MERSİS dalında None atanır (doğrulanabilir algoritma yok) — açık tip şart.
    checksum: bool | None
    if resolved is IdentifierKind.LEI:
        normalized = normalize_lei(value)
        well_formed = len(normalized) == LEI_LENGTH and normalized.isalnum()
        checksum = is_valid_lei(normalized) if well_formed else False
        reason = None if well_formed else f"LEI {LEI_LENGTH} karakter olmalıdır."
        return IdentifierCheck(resolved, normalized, well_formed, checksum, reason)

    normalized = normalize_digits(value)
    if resolved is IdentifierKind.TCKN:
        well_formed = len(normalized) == TCKN_LENGTH and normalized[0:1] != "0"
        checksum = is_valid_tckn(normalized) if well_formed else False
        reason = None if well_formed else "TCKN 11 haneli olmalı ve 0 ile başlamamalıdır."
    elif resolved is IdentifierKind.VKN:
        well_formed = len(normalized) == VKN_LENGTH
        checksum = is_valid_vkn(normalized) if well_formed else False
        reason = None if well_formed else "Vergi kimlik numarası 10 haneli olmalıdır."
    else:  # MERSİS
        well_formed = is_well_formed_mersis(normalized)
        checksum = None  # doğrulanabilir bir algoritma yok
        reason = None if well_formed else "MERSİS numarası 16 haneli olmalıdır."

    if well_formed and checksum is False:
        reason = "Kontrol basamağı tutmuyor — numarayı belgeden teyit edin."
    return IdentifierCheck(resolved, normalized, well_formed, checksum, reason)
