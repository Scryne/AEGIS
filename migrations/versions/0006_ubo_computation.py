"""UBO hesap anlık görüntüsü: ubo_computation (RLS + saklama süresi)

Revision ID: 0006_ubo_computation
Revises: 0005_report
Create Date: 2026-10-31

Invariant 1 (CLAUDE.md, ADR-0002): ``ubo_computation`` kiracıya-özel bir *veri* tablosudur →
``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu migration'ın
içindedir ve tablo kiracılar-arası izolasyon kapısına aynı değişiklikte eklenmiştir.

Invariant 4: ``retention_until`` doğuştan vardır — UBO kararı yükümlülüğün kanıtıdır.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_ubo_computation"
down_revision: str | None = "0005_report"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ubo_computation",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("threshold_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("threshold_inclusive", sa.Boolean(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("computed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_ubo_computation_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_ubo_computation_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ubo_computation")),
    )
    op.create_index(op.f("ix_ubo_computation_tenant_id"), "ubo_computation", ["tenant_id"])
    op.create_index(op.f("ix_ubo_computation_entity_id"), "ubo_computation", ["entity_id"])
    op.create_index(
        op.f("ix_ubo_computation_retention_until"), "ubo_computation", ["retention_until"]
    )
    op.create_index(
        "ix_ubo_computation_entity_id_created_at", "ubo_computation", ["entity_id", "created_at"]
    )

    # Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001).
    op.execute("ALTER TABLE ubo_computation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ubo_computation FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ubo_computation_tenant_isolation ON ubo_computation "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ubo_computation_tenant_isolation ON ubo_computation")
    op.drop_table("ubo_computation")
