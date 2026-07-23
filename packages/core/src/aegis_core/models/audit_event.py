"""AuditEvent — değiştirilemez (append-only) denetim izi + kiracı-başına hash zinciri.

CLAUDE.md Invariant 2: risk-etkileyen her eylem (tarama çalıştırma, eşleşme onay/ret,
rapor dışa aktarma, varlık düzenleme) tam olarak **bir** olay yazar. Tablo:

- Kiracıya-özeldir → ``TenantMixin`` + ENABLE/FORCE RLS (bkz. migration 0002).
- Append-only'dir → ``aegis_app`` rolünden UPDATE/DELETE REVOKE edilir **ve** bir
  BEFORE UPDATE/DELETE trigger'ı her mutasyonu RAISE ile reddeder (çift katman).
- Kurcalamaya-dayanıklıdır → her satır bir hash zinciri taşır:
  ``row_hash = H(prev_hash ‖ canonical_payload)``, kiracı başına ``seq`` ile sıralı.
  Trigger'ı devre dışı bırakabilen bir DBA bile geçmişi sessizce değiştiremez —
  ``verify_chain`` kopuşu yakalar (bkz. ``services/audit.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class AuditAction(StrEnum):
    """Denetlenen eylem türleri (nokta-ayraçlı ad uzayı; ``String`` olarak saklanır).

    Yeni eylemler migration gerektirmeden buraya eklenir (DB düzeyinde enum kısıtı
    yoktur; değer ``action`` string kolonunda tutulur). E1.3+ geldikçe tarama/eşleşme
    eylemleri kullanılmaya başlanır; şimdilik yalnız ``TENANT_SETTING_UPDATE`` yayılır.
    """

    TENANT_SETTING_UPDATE = "tenant_setting.update"
    # E1.3+ risk-etkileyen eylemler (CLAUDE.md Invariant 2) — geldikçe yayılacak:
    SCREENING_RUN = "screening.run"
    MATCH_CONFIRM = "match.confirm"
    MATCH_DISMISS = "match.dismiss"
    REPORT_EXPORT = "report.export"
    ENTITY_EDIT = "entity.edit"


class AuditEvent(UUIDPKMixin, TenantMixin, Base):
    """Değiştirilemez denetim olayı (hash zincirinin bir halkası).

    ``TimestampMixin`` bilinçli olarak kullanılmaz: tablo değiştirilemez olduğundan
    ``updated_at`` anlamsızdır. Olay zamanı, hash'e dahil olan ``occurred_at``tir ve
    determinizm için Python tarafında (UTC) üretilir.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        # Kiracı başına ``seq`` tekildir: zincir bütünlüğü + eşzamanlı yazımda
        # yarışı DB düzeyinde de yakalayan emniyet kemeri.
        UniqueConstraint("tenant_id", "seq", name="uq_audit_event_tenant_id_seq"),
    )

    # Kiracı başına monotonik sıra (1'den başlar) — hash zincirinin sırası.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Eylemi yapan. FK YOK: denetim izi, kullanıcı sonradan silinse de aktörü korur
    # (append-only geçmiş, kimlik tablosunun yaşam döngüsünden bağımsızdır).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # Eylemin hedefi (doğal anahtarla; ör. "tenant_setting" + anahtar string'i).
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Kaynak referansı (Invariant 4): bulgunun/kaydın kanıt bağlantısı (URL, veri
    # kümesi sürümü, belge kimliği). Her eylemde olmayabilir → nullable.
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Eylemin yapısal ayrıntısı (eski/yeni değer, skor, veri kümesi …); hash'e girer.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Hash zinciri: prev_hash ilk halkada genesis sabitidir (bkz. services/audit.py).
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
