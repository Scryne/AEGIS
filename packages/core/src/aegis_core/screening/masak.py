"""MASAK malvarlığı dondurma listelerini FtM veri kümesine çevirir (E1.3).

OpenSanctions, 6415 sayılı Kanun kapsamındaki **yurtiçi** MASAK kararlarını eksiksiz
taşımaz. Türkiye'de faaliyet gösteren bir yükümlü için bu liste tam olarak asıl
denetlenen listedir; bu yüzden yente'ye **özel bir FtM veri kümesi** olarak enjekte
edilir (``masak_dondurma``) ve OpenSanctions'la birlikte tek kapsamda sorgulanır.

Akış::

    kaynak dosya (CSV/JSON)  →  parse_records  →  to_ftm_entities  →  entities.ftm.json
                                                                          ↓
                                              yente manifest (infra/yente/manifest.yml)
                                                                          ↓
                                                     günlük ``sanctions.sync`` reindex

**Kaynak biçimi hakkında dürüst not.** MASAK listeleri kararname ekleri olarak yayımlanır
ve makine-okur, sürümlenmiş bir API'si yoktur. Bu modül, sütun adları eşlenebilir bir
CSV ile FtM'e giden yolu **eksiksiz** kurar; doğrulanması gereken tek şey üstteki
dosyanın güncel sütun düzenidir (``COLUMN_ALIASES``). Alias tablosu, biçim değişirse
kodun geri kalanına dokunulmadan güncellenecek şekilde ayrılmıştır.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aegis_core.logging import get_logger
from aegis_core.screening.normalization import (
    SubjectType,
    canonicalize,
    normalize_name,
    to_ascii,
)

logger = get_logger("aegis.screening.masak")

# yente/FtM tarafında bu veri kümesindeki her kayda basılan konu etiketi.
SANCTION_TOPIC = "sanction"
DEFAULT_DATASET_NAME = "masak_dondurma"
DEFAULT_DATASET_TITLE = "MASAK Malvarlığı Dondurma Listeleri (6415 s. Kanun)"

# Kaynak CSV sütun adları → iç alan adları. Başlıklar kanonikleştirilip **ASCII'ye**
# indirgenerek eşlenir (bkz. ``_alias_key``): "Adı Soyadı", "ADI SOYADI" ve "Adi Soyadi"
# aynı anahtara iner, böylece kaynak dosyanın imla tercihleri eşlemeyi bozmaz.
COLUMN_ALIASES: dict[str, str] = {
    "adi soyadi": "name",
    "ad soyad": "name",
    "adi": "name",
    "unvan": "name",
    "unvani": "name",
    "kurulus adi": "name",
    "isim": "name",
    "dogum tarihi": "birth_date",
    "dogum yeri": "birth_place",
    "uyrugu": "nationality",
    "uyruk": "nationality",
    "pasaport no": "passport_number",
    "kimlik no": "id_number",
    "tc kimlik no": "id_number",
    "vergi no": "tax_number",
    "adres": "address",
    "karar no": "decision_number",
    "karar tarihi": "decision_date",
    "dayanak": "legal_basis",
    "madde": "legal_basis",
    "aciklama": "notes",
    "tur": "record_type",
}

_PERSON_HINTS = ("gercek", "kisi", "person", "sahis")
_COMPANY_HINTS = ("tuzel", "kurulus", "sirket", "company", "organization")


def _alias_key(text: str) -> str:
    """Sütun başlığını/tür etiketini eşleme anahtarına indirger (kanonik + ASCII)."""
    return to_ascii(canonicalize(text))


@dataclass(frozen=True)
class FreezeListRecord:
    """MASAK listesindeki tek bir kayıt (kaynak biçiminden bağımsız iç temsil)."""

    name: str
    record_type: SubjectType
    birth_date: str | None = None
    birth_place: str | None = None
    nationality: str | None = None
    passport_number: str | None = None
    id_number: str | None = None
    tax_number: str | None = None
    address: str | None = None
    decision_number: str | None = None
    decision_date: str | None = None
    legal_basis: str | None = None
    notes: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


def _clean(value: object) -> str | None:
    """Boşlukları kırpar; boş/anlamsız değerleri ``None`` yapar."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "yok", "bilinmiyor"}:
        return None
    return text


def _guess_record_type(raw_type: str | None, name: str) -> SubjectType:
    """Kayıt türünü belirler: açık sütun yoksa unvandaki tüzel ekten çıkarır.

    Tür yanlış tahmin edilirse eşleştirme şeması yanlış olur (``Person`` vs ``Company``)
    ve eşleşme kaçabilir; bu yüzden ipucu yoksa **şirket** varsayılmaz — ad tüzel ek
    taşımıyorsa kişi kabul edilir, çünkü dondurma listelerinin ağırlığı gerçek kişidir.
    """
    if raw_type:
        normalized_type = _alias_key(raw_type)
        if any(hint in normalized_type for hint in _COMPANY_HINTS):
            return SubjectType.COMPANY
        if any(hint in normalized_type for hint in _PERSON_HINTS):
            return SubjectType.PERSON
    # Unvanda tüzel-kişilik eki tespit edilirse şirkettir.
    if normalize_name(name, SubjectType.COMPANY).stripped:
        return SubjectType.COMPANY
    return SubjectType.PERSON


def _map_row(row: Mapping[str, Any]) -> dict[str, str | None]:
    """Kaynak satırının sütunlarını iç alan adlarına eşler (tanınmayanlar ``extra``ya)."""
    mapped: dict[str, str | None] = {}
    extra: dict[str, str] = {}
    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue
        field_name = COLUMN_ALIASES.get(_alias_key(str(raw_key)))
        value = _clean(raw_value)
        if field_name is None:
            if value is not None:
                extra[str(raw_key).strip()] = value
            continue
        mapped[field_name] = value
    mapped["_extra"] = json.dumps(extra, ensure_ascii=False) if extra else None
    return mapped


def parse_records(rows: Iterable[Mapping[str, Any]]) -> list[FreezeListRecord]:
    """Satır sözlüklerini ``FreezeListRecord``lara çevirir; adsız satırları atar."""
    records: list[FreezeListRecord] = []
    skipped = 0
    for row in rows:
        mapped = _map_row(row)
        name = mapped.get("name")
        if not name:
            skipped += 1
            continue
        extra_raw = mapped.get("_extra")
        records.append(
            FreezeListRecord(
                name=name,
                record_type=_guess_record_type(mapped.get("record_type"), name),
                birth_date=mapped.get("birth_date"),
                birth_place=mapped.get("birth_place"),
                nationality=mapped.get("nationality"),
                passport_number=mapped.get("passport_number"),
                id_number=mapped.get("id_number"),
                tax_number=mapped.get("tax_number"),
                address=mapped.get("address"),
                decision_number=mapped.get("decision_number"),
                decision_date=mapped.get("decision_date"),
                legal_basis=mapped.get("legal_basis"),
                notes=mapped.get("notes"),
                extra=json.loads(extra_raw) if extra_raw else {},
            )
        )
    if skipped:
        logger.warning("masak_adsiz_satir_atlandi", count=skipped)
    return records


def parse_csv(content: str, *, delimiter: str | None = None) -> list[FreezeListRecord]:
    """CSV metnini kayıtlara çevirir (ayraç verilmezse otomatik sezilir)."""
    sample = content[:4096]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ";"  # Türkçe Excel çıktılarının yaygın ayracı
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    return parse_records(reader)


def _entity_id(record: FreezeListRecord, dataset_name: str) -> str:
    """Kayıt için kararlı (deterministik) bir varlık kimliği üretir.

    Kaynakta kalıcı bir kimlik yoktur; ad + doğum tarihi + karar numarasından türetilen
    kararlı bir hash kullanılır. Kararlı olması şart: her yenilemede kimlik değişseydi
    onaylanmış/elenmiş eşleşmelerin bağı kopardı.
    """
    normalized = normalize_name(record.name, record.record_type)
    seed = "|".join(
        [
            normalized.sort_key,
            record.birth_date or "",
            record.decision_number or "",
            record.legal_basis or "",
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{dataset_name}-{digest}"


def _append(properties: dict[str, list[str]], key: str, value: str | None) -> None:
    if value:
        properties.setdefault(key, []).append(value)


def to_ftm_entities(
    records: Sequence[FreezeListRecord],
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
    source_url: str | None = None,
) -> list[dict[str, Any]]:
    """Kayıtları yente'nin okuduğu FtM varlık sözlüklerine çevirir.

    Her varlık ``topics: ["sanction"]`` taşır — risk özeti (E1.5) ve eşik bandı bu
    etikete bakar. ``sourceUrl`` her kayda basılır: bulgunun kanıt bağlantısı
    (Invariant 4) MASAK kararına işaret etmelidir.
    """
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        entity_id = _entity_id(record, dataset_name)
        if entity_id in seen:
            continue
        seen.add(entity_id)

        normalized = normalize_name(record.name, record.record_type)
        properties: dict[str, list[str]] = {"name": [record.name], "topics": [SANCTION_TOPIC]}
        # Kanonik ve ASCII biçimler takma ad olarak eklenir: liste "ŞAHİN" yazarken
        # kullanıcı "Sahin" arayabilir (ya da tersi).
        for alias in {normalized.canonical, normalized.ascii} - {record.name}:
            _append(properties, "alias", alias)
        _append(properties, "birthDate", record.birth_date)
        _append(properties, "birthPlace", record.birth_place)
        _append(properties, "nationality", record.nationality)
        _append(properties, "passportNumber", record.passport_number)
        _append(properties, "idNumber", record.id_number)
        _append(properties, "taxNumber", record.tax_number)
        _append(properties, "address", record.address)
        _append(properties, "sourceUrl", source_url)
        _append(properties, "program", _program_label(record))
        _append(properties, "notes", record.notes)
        if record.record_type is SubjectType.COMPANY:
            _append(properties, "country", "tr")
        else:
            _append(properties, "country", record.nationality or "tr")

        entities.append(
            {
                "id": entity_id,
                "schema": "Person" if record.record_type is SubjectType.PERSON else "Company",
                "properties": properties,
                "datasets": [dataset_name],
            }
        )
    return entities


def _program_label(record: FreezeListRecord) -> str:
    """Kararın insan-okur etiketi (raporlarda "hangi karara göre" satırı)."""
    parts = ["MASAK malvarlığı dondurma"]
    if record.legal_basis:
        parts.append(record.legal_basis)
    if record.decision_number:
        parts.append(f"Karar {record.decision_number}")
    if record.decision_date:
        parts.append(record.decision_date)
    return " · ".join(parts)


def write_entities_file(entities: Sequence[Mapping[str, Any]], path: Path) -> int:
    """Varlıkları yente'nin beklediği JSON-lines dosyasına yazar; satır sayısını döndürür.

    Yazım **atomiktir** (önce ``.tmp``, sonra ``replace``): yente aynı anda okuyorsa
    yarım dosya görmemelidir.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for entity in entities:
            handle.write(json.dumps(entity, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)
    return len(entities)


def build_dataset_file(
    content: str,
    destination: Path,
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
    source_url: str | None = None,
) -> int:
    """CSV içeriğini uçtan uca FtM dosyasına çevirir; yazılan varlık sayısını döndürür."""
    records = parse_csv(content)
    entities = to_ftm_entities(records, dataset_name=dataset_name, source_url=source_url)
    written = write_entities_file(entities, destination)
    logger.info(
        "masak_veri_kumesi_yazildi",
        dataset=dataset_name,
        records=len(records),
        entities=written,
        path=str(destination),
    )
    return written


_DIGITS = re.compile(r"\D+")


def normalize_identifier(value: str) -> str:
    """Kimlik/vergi numarasını yalnız rakamlara indirger (biçim farklarını siler)."""
    return _DIGITS.sub("", value)
