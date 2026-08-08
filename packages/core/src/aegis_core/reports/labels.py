"""Rapor metinlerinin Türkçe etiketleri (E1.5).

Arayüzdeki etiketler ``apps/web/src/lib/entities.ts`` içindedir; rapor sunucuda
üretildiği için aynı sözlüğün Python karşılığı burada durur. İkisi **bilinçli olarak
kopyadır**: raporu üretmek için Node çalıştırmak ya da etiketleri API'den taşımak,
tek-host duruşuna (R6) değmeyecek bir bağ kurardı. Etiket değişince iki dosya birlikte
güncellenir — tümü tek ekranlık sabit sözlüklerdir.
"""

from __future__ import annotations

from datetime import date, datetime

ATTRIBUTE_LABELS: dict[str, str] = {
    "name": "Unvan / ad",
    "address": "Adres",
    "country": "Ülke",
    "taxNumber": "Vergi no",
    "mersisNumber": "MERSİS no",
    "leiCode": "LEI",
    "tradeRegistryNumber": "Ticaret sicil no",
    "nationalId": "T.C. kimlik no",
    "incorporationDate": "Kuruluş tarihi",
    "birthDate": "Doğum tarihi",
}

SOURCE_LABELS: dict[str, str] = {
    "declared": "Beyan",
    "document": "Belge",
    "registry": "Kütük",
    "gleif": "GLEIF",
    "screening": "Tarama",
}

REL_TYPE_LABELS: dict[str, str] = {
    "officer": "Yönetici",
    "shareholder": "Ortak",
    "ubo": "Gerçek faydalanıcı",
    "family": "Aile bağı",
    "control": "Kontrol",
    "representative": "Temsilci",
}

DOC_TYPE_LABELS: dict[str, str] = {
    "imza_sirkuleri": "İmza sirküleri",
    "faaliyet_belgesi": "Faaliyet belgesi",
    "ticaret_sicil_gazetesi": "Ticaret Sicil Gazetesi",
    "other": "Diğer",
}

SEVERITY_LABELS: dict[str, str] = {
    "info": "Bilgi",
    "warning": "Uyarı",
    "critical": "Kritik",
}

DISCREPANCY_STATUS_LABELS: dict[str, str] = {
    "open": "Açık",
    "accepted": "Açıklandı ve kabul edildi",
    "resolved": "Düzeltildi",
}

DECISION_LABELS: dict[str, str] = {
    "pending": "Karar bekliyor",
    "confirmed": "Onaylandı",
    "dismissed": "Elendi",
}

BAND_LABELS: dict[str, str] = {
    "auto_dismiss": "Otomatik eleme bandı",
    "review": "İnceleme bandı",
    "auto_flag": "Otomatik işaretleme bandı",
}

SCREENING_STATUS_LABELS: dict[str, str] = {
    "queued": "Sırada",
    "running": "Çalışıyor",
    "completed": "Tamamlandı",
    "failed": "Başarısız — sonuç yok",
}

SUBJECT_ROLE_LABELS: dict[str, str] = {
    "self": "Şirketin kendisi",
    "officer": "Yönetici",
    "ubo": "Gerçek faydalanıcı",
    "shareholder": "Ortak",
}

SCHEMA_LABELS: dict[str, str] = {
    "Person": "Gerçek kişi",
    "Company": "Tüzel kişi",
}


def label(mapping: dict[str, str], key: str | None) -> str:
    """Sözlükten etiket döndürür; tanınmayan anahtarı **gizlemez**, ham hâliyle gösterir."""
    if key is None:
        return "—"
    return mapping.get(key, key)


def format_datetime(value: datetime | None) -> str:
    """Tarih-saati rapor biçiminde yazar (gg.aa.yyyy SS:DD)."""
    return "—" if value is None else value.strftime("%d.%m.%Y %H:%M")


def format_date(value: date | None) -> str:
    """Tarihi rapor biçiminde yazar (gg.aa.yyyy)."""
    return "—" if value is None else value.strftime("%d.%m.%Y")


def format_value(value: object) -> str:
    """Boş değerleri tire ile gösterir (rapor tablolarında boş hücre bırakmamak için)."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return format_datetime(value)
    if isinstance(value, date):
        return format_date(value)
    text = str(value).strip()
    return text or "—"
