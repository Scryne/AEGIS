"""Türkçe belgelerden veri çıkarımı — imza sirküleri / faaliyet belgesi (E1.4, R2).

**Saf metin işidir.** PDF'i metne çeviren motor (Docling) ayrı bir adaptördedir; burada
yalnız metin → yapılandırılmış öneri dönüşümü vardır. Bu ayrım bilinçlidir: hataların
büyük çoğunluğu desen eşleştirmede olur ve o kısım Docling kurulu olmadan, gerçek belge
metinlerine benzeyen fixture'larla test edilebilmelidir.

**Güven skoru (confidence) nasıl kurulur.** Bir sayının gerçekten vergi numarası olduğuna
üç kanıt katkı verir: (1) yanında etiketi var mı ("Vergi No:"), (2) kontrol basamağı
tutuyor mu, (3) beklenen uzunlukta mı. Faaliyet belgesinde tarih, sermaye, sicil no ve
telefon da rakam öbeğidir; kontrol basamağı bunları ayıklayan asıl filtredir.

**Hiçbir çıkarım doğrudan kütüğe yazılmaz.** Sonuç ``ExtractionProposal`` satırlarına
dönüşür ve insan onayı bekler (Revizyon R2). Bu yüzden burada "emin değilsek atma"
yerine "düşük güvenle öner" tercih edilir: kaçan bir yönetici adı, yanlış önerilenden
pahalıdır — kullanıcı yanlışı tek tıkla reddeder, eksiği fark etmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aegis_core.entities.identifiers import (
    is_valid_tckn,
    is_valid_vkn,
    normalize_digits,
)
from aegis_core.screening.normalization import SubjectType as _SubjectType
from aegis_core.screening.normalization import normalize_name

# Türkçe büyük/küçük harf sınıfları (regex'te \w yeterli ayrım yapmaz).
_UPPER = "A-ZÇĞİÖŞÜ"
_LOWER = "a-zçğıöşü"

# Güven skorları — kanıt birikimine göre.
CONF_LABELLED_CHECKSUM = 0.95
CONF_LABELLED = 0.85
CONF_LABELLED_BAD_CHECKSUM = 0.50
CONF_UNLABELLED_CHECKSUM = 0.60
CONF_PERSON_WITH_ROLE = 0.85
CONF_PERSON_ONLY = 0.55

# Tüzel kişilik eki içeren satır, şirket unvanı adayıdır.
#
# Sözcük sınırları ŞART: sınırsız hâlde "a ş" kalıbı "aşağıda", "aşama" gibi sıradan
# sözcüklerin içinde eşleşiyor ve alakasız satırları şirket unvanı sanıyordu.
_LEGAL_FORM_HINT = re.compile(
    r"(?<!\w)"
    r"(a\.?\s*ş\.?|anonim\s+şirketi|ltd\.?\s*şti\.?|limited\s+şirketi|koll\.?\s*şti\.?"
    r"|komandit\s+şirketi)"
    r"(?!\w)",
    re.IGNORECASE,
)

_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")

# İmza sirkülerinde yetkiyi işaretleyen ifadeler.
_AUTHORITY_HINTS = (
    "münferiden",
    "müştereken",
    "temsil ve ilzama yetkili",
    "temsile yetkili",
    "imza yetkisi",
    "yönetim kurulu",
    "müdür",
)

# Kişi adı: 2–4 ardışık, büyük harfle başlayan sözcük. Belgelerde adlar çoğunlukla
# TAMAMEN BÜYÜK yazılır; her iki yazımı da kabul ederiz.
_PERSON_NAME = re.compile(
    rf"\b([{_UPPER}][{_UPPER}{_LOWER}]+(?:\s+[{_UPPER}][{_UPPER}{_LOWER}]+){{1,3}})\b"
)

# Kişi adı sanılmaması gereken kurumsal/biçimsel sözcükler.
_NAME_STOPWORDS = frozenset(
    {
        "ticaret",
        "sicil",
        "odası",
        "vergi",
        "dairesi",
        "kimlik",
        "numarası",
        "yönetim",
        "kurulu",
        "genel",
        "müdür",
        "müdürü",
        "başkanı",
        "üyesi",
        "şirket",
        "şirketi",
        "anonim",
        "limited",
        "faaliyet",
        "belgesi",
        "imza",
        "sirküleri",
        "adres",
        "merkez",
        "sermaye",
        "tarih",
        "tarihi",
        "sayfa",
        "noter",
        "türkiye",
        "cumhuriyeti",
        "mersis",
        "ünvanı",
        "unvanı",
        "temsil",
        "ilzam",
        "yetkili",
        "müştereken",
        "münferiden",
        "kuruluş",
        "tescil",
        "konusu",
        "işletme",
    }
)


@dataclass(frozen=True)
class ExtractedAttribute:
    """Belgeden çıkan bir öznitelik önerisi."""

    name: str
    """FtM öznitelik adı (``taxNumber``, ``address`` …)."""

    value: str
    confidence: float
    evidence: str
    page: int | None = None


@dataclass(frozen=True)
class ExtractedPerson:
    """Belgeden çıkan bir kişi–şirket bağı önerisi."""

    name: str
    rel_type: str = "officer"
    role_title: str | None = None
    national_id: str | None = None
    confidence: float = CONF_PERSON_ONLY
    evidence: str = ""
    page: int | None = None


@dataclass(frozen=True)
class ExtractionResult:
    """Bir belgeden çıkan tüm öneriler."""

    attributes: list[ExtractedAttribute] = field(default_factory=list)
    persons: list[ExtractedPerson] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Hiçbir öneri üretilmedi mi (kullanıcıya "okunamadı" demek için)."""
        return not self.attributes and not self.persons


def _labelled_value(text: str, labels: tuple[str, ...], pattern: str) -> tuple[str, str] | None:
    """Etiketten sonra gelen değeri yakalar; (değer, kanıt satırı) döndürür."""
    for label in labels:
        regex = re.compile(
            rf"{label}\s*[:\-–]?\s*({pattern})",
            re.IGNORECASE | re.UNICODE,
        )
        match = regex.search(text)
        if match:
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            evidence = text[line_start : line_end if line_end != -1 else len(text)].strip()
            # Kanıt satırı şifresiz saklanır → içindeki TCKN maskelenir (KVKK).
            return match.group(1).strip(), redact_national_ids(evidence)
    return None


def _extract_identifier(
    text: str,
    *,
    labels: tuple[str, ...],
    length: int,
    attribute: str,
    validator: object = None,
) -> ExtractedAttribute | None:
    """Etiketli bir kimlik numarasını çıkarır ve kontrol basamağına göre güven verir."""
    found = _labelled_value(text, labels, r"[\d\s.\-]{" + str(length) + r",}")
    if found is None:
        return None
    raw, evidence = found
    digits = normalize_digits(raw)[:length]
    if len(digits) != length:
        return None

    if callable(validator):
        confidence = CONF_LABELLED_CHECKSUM if validator(digits) else CONF_LABELLED_BAD_CHECKSUM
    else:
        confidence = CONF_LABELLED
    return ExtractedAttribute(
        name=attribute, value=digits, confidence=confidence, evidence=evidence
    )


def _extract_unlabelled_tax_number(text: str) -> ExtractedAttribute | None:
    """Etiketsiz 10 haneli sayılar arasında kontrol basamağı tutan **tek** adayı arar.

    Birden çok aday varsa hiçbiri önerilmez: belgede birbirine karışan iki numaradan
    yanlışını seçmek, hiç seçmemekten kötüdür (kullanıcı eksiği elle girer, yanlışı
    fark etmeyebilir).
    """
    candidates = {
        match.group(0)
        for match in re.finditer(r"(?<!\d)\d{10}(?!\d)", text)
        if is_valid_vkn(match.group(0))
    }
    if len(candidates) != 1:
        return None
    value = candidates.pop()
    index = text.find(value)
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    evidence = text[line_start : line_end if line_end != -1 else len(text)].strip()
    return ExtractedAttribute(
        name="taxNumber",
        value=value,
        confidence=CONF_UNLABELLED_CHECKSUM,
        evidence=evidence,
    )


def _extract_company_title(text: str) -> ExtractedAttribute | None:
    """Tüzel kişilik eki taşıyan en uzun satırı şirket unvanı adayı sayar."""
    labelled = _labelled_value(
        text, ("ticaret unvanı", "ticaret ünvanı", "unvanı", "ünvanı", "firma"), r"[^\n]+"
    )
    if labelled is not None:
        value, evidence = labelled
        value = value.strip(" .:-")
        if value:
            return ExtractedAttribute(
                name="name", value=value, confidence=CONF_LABELLED, evidence=evidence
            )

    best: str | None = None
    for line in text.splitlines():
        stripped = line.strip(" .:-")
        if len(stripped) < 8 or not _LEGAL_FORM_HINT.search(stripped):
            continue
        if best is None or len(stripped) > len(best):
            best = stripped
    if best is None:
        return None
    return ExtractedAttribute(
        name="name", value=best, confidence=CONF_UNLABELLED_CHECKSUM, evidence=best
    )


def _extract_address(text: str) -> ExtractedAttribute | None:
    found = _labelled_value(
        text, ("merkez adresi", "adresi", "adres", "işyeri adresi"), r"[^\n]{10,}"
    )
    if found is None:
        return None
    value, evidence = found
    return ExtractedAttribute(
        name="address", value=value.strip(" .:-"), confidence=CONF_LABELLED, evidence=evidence
    )


def _extract_date(text: str, labels: tuple[str, ...], attribute: str) -> ExtractedAttribute | None:
    """Etiketli bir tarihi ISO biçimine çevirir."""
    found = _labelled_value(text, labels, r"\d{1,2}[./-]\d{1,2}[./-]\d{4}")
    if found is None:
        return None
    raw, evidence = found
    match = _DATE.search(raw)
    if match is None:  # pragma: no cover - desen zaten eşleşti
        return None
    day, month, year = (int(part) for part in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return ExtractedAttribute(
        name=attribute,
        value=f"{year:04d}-{month:02d}-{day:02d}",
        confidence=CONF_LABELLED,
        evidence=evidence,
    )


def _looks_like_person_name(candidate: str) -> bool:
    """Aday metnin kişi adı olup olmadığına karar verir (kurumsal sözcükleri eler)."""
    words = candidate.split()
    if not 2 <= len(words) <= 4:
        return False
    for word in words:
        lowered = normalize_name(word, _SubjectType.PERSON).canonical
        if lowered in _NAME_STOPWORDS:
            return False
        if len(word) < 2:
            return False
    return True


def redact_national_ids(text: str) -> str:
    """Metindeki **geçerli TCKN'leri** maskeler (KVKK).

    Kanıt metni ve yetki ifadesi kullanıcıya gösterilir ve ``extraction_proposal``
    tablosunda **şifresiz** saklanır; oraya düz TCKN yazmak, şifreli ``entity.national_id``
    kolonunu anlamsız kılardı. Vergi/MERSİS numaraları maskelenmez: onlar tüzel kişilerin
    kamuya açık tanımlayıcılarıdır ve kanıtın okunabilirliği için gereklidir.
    """

    def _mask(match: re.Match[str]) -> str:
        value = match.group(0)
        return "*" * (len(value) - 4) + value[-4:] if is_valid_tckn(value) else value

    return re.sub(r"(?<!\d)\d{11}(?!\d)", _mask, text)


def _role_for_line(line: str) -> str | None:
    """Satırda yetki/unvan ifadesi varsa **o satırı** döndürür (kimlik no maskeli).

    Bilinçli olarak yalnız eşleşen satır döner: bağlamın tamamını almak, kişinin adını
    ve kimlik numarasını unvan metnine taşıyordu — hem çirkin hem KVKK açısından yanlış.
    """
    for candidate in line.splitlines() or [line]:
        lowered = candidate.lower()
        if any(hint in lowered for hint in _AUTHORITY_HINTS):
            return redact_national_ids(candidate.strip(" .:-"))[:255]
    return None


def _extract_persons(text: str) -> list[ExtractedPerson]:
    """Yetki bağlamındaki kişi adlarını ve (varsa) TCKN'lerini çıkarır.

    Her satır ve bir sonraki satır birlikte değerlendirilir: imza sirkülerinde ad bir
    satırda, yetki ifadesi genelde aynı ya da bitişik satırdadır.
    """
    lines = text.splitlines()
    persons: dict[str, ExtractedPerson] = {}

    for index, line in enumerate(lines):
        # Satır sonları KORUNUR: ``_role_for_line`` yetki ifadesinin geçtiği TEK satırı
        # seçebilsin diye (düz birleştirme, kişinin adını unvan metnine taşıyordu).
        context = "\n".join(lines[index : index + 2])
        role = _role_for_line(line) or _role_for_line(context)

        for match in _PERSON_NAME.finditer(line):
            candidate = match.group(1).strip()
            if not _looks_like_person_name(candidate):
                continue
            # Aynı satırdaki geçerli bir TCKN kişiye bağlanır.
            tckn = next(
                (
                    number
                    for number in re.findall(r"(?<!\d)\d{11}(?!\d)", context)
                    if is_valid_tckn(number)
                ),
                None,
            )
            confidence = CONF_PERSON_WITH_ROLE if role else CONF_PERSON_ONLY
            if tckn:
                confidence = min(1.0, confidence + 0.1)
            key = normalize_name(candidate, _SubjectType.PERSON).sort_key
            existing = persons.get(key)
            if existing is not None and existing.confidence >= confidence:
                continue
            persons[key] = ExtractedPerson(
                name=candidate,
                rel_type="officer",
                role_title=role,
                national_id=tckn,
                confidence=confidence,
                # Kanıt metni kullanıcıya gösterilir ve şifresiz saklanır → TCKN maskeli.
                evidence=redact_national_ids(context.strip())[:500],
            )
    return list(persons.values())


def extract_from_text(text: str, doc_type: str) -> ExtractionResult:
    """Belge metninden öznitelik ve kişi önerileri çıkarır.

    ``doc_type`` yalnız **hangi çıkarımların denenmesi gerektiğini** belirler; desenler
    ortaktır, çünkü sahada belgeler birbirine karışır (faaliyet belgesinde de yetkili
    listesi bulunabilir).
    """
    if not text or not text.strip():
        return ExtractionResult(warnings=["Belgeden metin çıkarılamadı (boş içerik)."])

    attributes: list[ExtractedAttribute] = []
    warnings: list[str] = []

    title = _extract_company_title(text)
    if title is not None:
        attributes.append(title)

    tax = _extract_identifier(
        text,
        labels=("vergi kimlik numarası", "vergi kimlik no", "vergi numarası", "vergi no", "vkn"),
        length=10,
        attribute="taxNumber",
        validator=is_valid_vkn,
    ) or _extract_unlabelled_tax_number(text)
    if tax is not None:
        attributes.append(tax)

    mersis = _extract_identifier(
        text,
        labels=("mersis numarası", "mersis no", "mersis"),
        length=16,
        attribute="mersisNumber",
    )
    if mersis is not None:
        attributes.append(mersis)

    registry = _labelled_value(
        text,
        ("ticaret sicil numarası", "ticaret sicil no", "sicil numarası", "sicil no"),
        r"[\w/-]+",
    )
    if registry is not None:
        attributes.append(
            ExtractedAttribute(
                name="tradeRegistryNumber",
                value=registry[0].strip(" .:-"),
                confidence=CONF_LABELLED,
                evidence=registry[1],
            )
        )

    address = _extract_address(text)
    if address is not None:
        attributes.append(address)

    incorporation = _extract_date(
        text, ("kuruluş tarihi", "tescil tarihi", "kayıt tarihi"), "incorporationDate"
    )
    if incorporation is not None:
        attributes.append(incorporation)

    persons = _extract_persons(text) if doc_type != "faaliyet_belgesi" else []
    if doc_type == "faaliyet_belgesi":
        # Faaliyet belgesinde de yetkili listesi olabilir; yalnız yetki ifadesi geçen
        # satırlardan çıkarılır (serbest ad taraması bu belgede çok gürültü üretir).
        persons = [person for person in _extract_persons(text) if person.role_title]

    if not attributes and not persons:
        warnings.append("Belgede tanınan bir alan bulunamadı; elle giriş gerekebilir.")

    return ExtractionResult(attributes=attributes, persons=persons, warnings=warnings)
