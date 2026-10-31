"""Kütükteki bir varlığı bağlı kişileriyle tarama — uç ve gece izleme görevi için ortak çekirdek.

``POST /screenings/from-entity/{id}`` (E1.3 × E1.4) ile izleme-lite'ın gece yeniden taraması
(E2.4) aynı özneleri, aynı eşiklerle taramalıdır; aksi halde gece koşusu ile elle koşu
arasındaki fark, gerçek bir liste değişikliği değil kod farkı olurdu.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.entities import service as entity_service
from aegis_core.models import Entity, SubjectRole
from aegis_core.screening.normalization import SubjectType
from aegis_core.screening.service import ScreeningInputError, ScreeningSubject
from aegis_core.screening.thresholds import SCREENING_THRESHOLD_SETTING_KEY, ScreeningThresholds
from aegis_core.services import tenant_settings as settings_service


async def load_thresholds(session: AsyncSession) -> ScreeningThresholds:
    """Kiracının eşik bandını okur; bozuk yapılandırmada taramayı reddeder.

    Sessizce varsayılana düşmek tehlikelidir: hatalı bir ``auto_dismiss_below``
    gerçek bir yaptırım eşleşmesini fark ettirmeden eleyebilirdi.
    """
    row = await settings_service.get_setting(session, SCREENING_THRESHOLD_SETTING_KEY)
    try:
        return ScreeningThresholds.from_mapping(row.value if row else None)
    except (ValueError, TypeError) as exc:
        raise ScreeningInputError(
            f"'{SCREENING_THRESHOLD_SETTING_KEY}' ayarı geçersiz: {exc}"
        ) from exc


async def subjects_for_entity(session: AsyncSession, entity: Entity) -> list[ScreeningSubject]:
    """Şirket + kütükte ona bağlı yönetici/ortak/UBO'lar. Kimlik numarası gönderilmez."""
    pairs = await entity_service.screening_subjects_for(session, entity)
    return [
        ScreeningSubject(
            name=item.name,
            subject_type=(
                SubjectType.PERSON if item.schema_type == "Person" else SubjectType.COMPANY
            ),
            role=SubjectRole(role)
            if role in {r.value for r in SubjectRole}
            else SubjectRole.OFFICER,
            country=item.country,
            identifiers=(
                {"taxNumber": item.tax_number} if item.tax_number and role == "self" else {}
            ),
        )
        for item, role in pairs
    ]
