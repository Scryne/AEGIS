"""Toplu tarama CSV içe aktarımı (E3.3) — saf çekirdek: çözme, ayraç, sütun eşleme, doğrulama.

ROADMAP E3.3: *"CSV import with column mapping + validation preview"*. Kurallar:

* **Kodlama:** önce UTF-8 (BOM'lu ya da değil), olmazsa Windows-1254 (Türkçe Excel'in "CSV"
  çıktısı). Ayraç ``;``, ``,`` ya da sekme; ilk satırdan seçilir.
* **Sütunlar:** ad/unvan (zorunlu), tür (şirket/kişi), vergi no, MERSİS, ülke, müşteri
  referansı. Başlıklar Türkçe ve İngilizce eş adlarla önerilir; kullanıcı eşlemeyi değiştirir.
* **TCKN kabul edilmez.** Kütükte TCKN şifreli saklanır (ADR-0005); toplu satır tablosu bu
  şifrelemeyi taşımaz. TCKN'ye benzeyen bir sütun eşlenmek istenirse dosya reddedilir; kişi
  kayıtları kimlik numarasıyla tek tek varlık formundan açılır.
* **Sınır:** en çok ``MAX_ROWS`` satır, ``MAX_BYTES`` bayt.
* Aynı dosyada tekrar eden satır (aynı vergi no, ya da vergi no yoksa aynı normalize ad + tür)
  ilk geçişe bağlanır ve ayrıca taranmaz.

Bu modül veritabanı bilmez; aynı bayt dizisi aynı sonucu verir.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from aegis_core.entities.identifiers import IdentifierKind, check_identifier
from aegis_core.screening.normalization import normalize_name

MAX_ROWS = 1000
MAX_BYTES = 2_000_000

FIELDS = ("name", "schema_type", "tax_number", "mersis_number", "country", "external_ref")
FIELD_LABELS = {
    "name": "Ad / unvan",
    "schema_type": "Tür (şirket/kişi)",
    "tax_number": "Vergi no",
    "mersis_number": "MERSİS no",
    "country": "Ülke",
    "external_ref": "Müşteri referansı",
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "name": (
        "ad",
        "adı",
        "unvan",
        "unvanı",
        "ad unvan",
        "ad soyad",
        "ticaret unvanı",
        "firma",
        "şirket",
        "sirket",
        "müşteri adı",
        "musteri adi",
        "name",
        "company",
        "full name",
    ),
    "schema_type": ("tür", "tur", "tip", "tipi", "kişi tipi", "type", "entity type", "schema"),
    "tax_number": ("vergi no", "vergi numarası", "vkn", "vergi kimlik no", "tax number", "tax id"),
    "mersis_number": ("mersis", "mersis no", "mersis numarası"),
    "country": ("ülke", "ulke", "country", "uyruk"),
    "external_ref": (
        "müşteri no",
        "musteri no",
        "referans",
        "ref",
        "id",
        "customer id",
        "cari kod",
        "kod",
    ),
}
_NATIONAL_ID_HEADERS = (
    "tckn",
    "tc kimlik",
    "tc kimlik no",
    "kimlik no",
    "t.c. kimlik no",
    "national id",
    "tc no",
)

_PERSON_WORDS = {"kişi", "kisi", "gerçek", "gercek", "gerçek kişi", "person", "individual", "şahıs"}
_COMPANY_WORDS = {
    "şirket",
    "sirket",
    "tüzel",
    "tuzel",
    "tüzel kişi",
    "company",
    "organization",
    "firma",
    "kurum",
    "",
}


class CsvImportError(ValueError):
    """Dosya bütünüyle reddedildi (kodlama, boyut, başlık, TCKN)."""


def _fold(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").replace(".", " ").split())


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise CsvImportError(f"Dosya {MAX_BYTES // 1_000_000} MB sınırını aşıyor.")
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvImportError("Dosya UTF-8 ya da Windows-1254 olarak okunamadı.")


def _delimiter(first_line: str) -> str:
    counts = {d: first_line.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


@dataclass
class ParsedCsv:
    headers: list[str]
    rows: list[list[str]]
    delimiter: str


def parse(data: bytes) -> ParsedCsv:
    text = decode(data)
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise CsvImportError("Dosya boş ya da başlık satırı yok.")
    delimiter = _delimiter(lines[0])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = [r for r in reader if any(cell.strip() for cell in r)]
    headers = [h.strip() for h in all_rows[0]]
    if len({_fold(h) for h in headers}) != len(headers):
        raise CsvImportError("Başlık satırında aynı adlı iki sütun var.")
    body = all_rows[1:]
    if not body:
        raise CsvImportError("Başlıktan sonra satır yok.")
    if len(body) > MAX_ROWS:
        raise CsvImportError(f"Dosyada {len(body)} satır var; en çok {MAX_ROWS} satır alınır.")
    return ParsedCsv(headers=headers, rows=body, delimiter=delimiter)


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """Alan → başlık önerisi (bulunamazsa ``None``)."""
    folded = {_fold(h): h for h in headers}
    out: dict[str, str | None] = {}
    for fname in FIELDS:
        out[fname] = next((folded[a] for a in _ALIASES[fname] if a in folded), None)
    return out


def national_id_headers(headers: list[str]) -> list[str]:
    return [h for h in headers if _fold(h) in _NATIONAL_ID_HEADERS]


def validate_mapping(headers: list[str], mapping: Mapping[str, str | None]) -> dict[str, str]:
    """Eşlemeyi denetler; yalnız dolu alanları döndürür."""
    unknown = [f for f in mapping if f not in FIELDS]
    if unknown:
        raise CsvImportError(f"Bilinmeyen alan: {', '.join(unknown)}")
    clean = {f: h for f, h in mapping.items() if h}
    if "name" not in clean:
        raise CsvImportError("Ad / unvan sütunu seçilmeli.")
    for fname, header in clean.items():
        if header not in headers:
            raise CsvImportError(f"'{header}' başlığı dosyada yok.")
        if _fold(header) in _NATIONAL_ID_HEADERS:
            raise CsvImportError(
                "TCKN sütunu toplu taramaya alınmaz (kütükte şifreli saklanır). "
                "Kişileri kimlik numarasıyla varlık formundan ekleyin."
            )
        del fname
    if len(set(clean.values())) != len(clean):
        raise CsvImportError("Aynı sütun iki alana eşlenemez.")
    return clean


@dataclass
class RowDraft:
    row_no: int
    """Dosyadaki satır numarası (başlık 1. satır; ilk veri satırı 2)."""

    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_of: int | None = None

    @property
    def valid(self) -> bool:
        return not self.errors


def _schema(raw: str) -> str | None:
    word = _fold(raw)
    if word in _PERSON_WORDS:
        return "Person"
    if word in _COMPANY_WORDS:
        return "Company"
    return None


def build_rows(parsed: ParsedCsv, mapping: Mapping[str, str]) -> list[RowDraft]:
    index = {h: i for i, h in enumerate(parsed.headers)}
    seen: dict[tuple[str, str], int] = {}
    out: list[RowDraft] = []
    for offset, cells in enumerate(parsed.rows):
        draft = RowDraft(row_no=offset + 2)

        def cell(fname: str, cells: list[str] = cells) -> str:
            header = mapping.get(fname)
            if not header:
                return ""
            i = index[header]
            return cells[i].strip() if i < len(cells) else ""

        name = " ".join(cell("name").split())
        if not name:
            draft.errors.append("Ad / unvan boş.")
        elif len(name) > 300:
            draft.errors.append("Ad / unvan 300 karakterden uzun.")
        schema = _schema(cell("schema_type"))
        if schema is None:
            draft.errors.append(f"Tür anlaşılamadı: '{cell('schema_type')}' (şirket ya da kişi).")
            schema = "Company"
        tax = cell("tax_number")
        if tax:
            check = check_identifier(IdentifierKind.VKN, tax)
            tax = check.normalized or tax
            if not check.looks_valid and check.reason:
                draft.warnings.append(f"Vergi no: {check.reason}")
        mersis = cell("mersis_number")
        if mersis:
            check = check_identifier(IdentifierKind.MERSIS, mersis)
            mersis = check.normalized or mersis
            if not check.looks_valid and check.reason:
                draft.warnings.append(f"MERSİS: {check.reason}")
        country = cell("country").upper()[:2] or None
        draft.data = {
            "name": name,
            "schema_type": schema,
            "tax_number": tax or None,
            "mersis_number": mersis or None,
            "country": country,
            "external_ref": cell("external_ref")[:100] or None,
        }
        if draft.valid:
            key = (
                ("tax", tax)
                if tax
                else (
                    schema,
                    normalize_name(name, "person" if schema == "Person" else "company").ascii,
                )
            )
            if key in seen:
                draft.duplicate_of = seen[key]
            else:
                seen[key] = draft.row_no
        out.append(draft)
    return out
