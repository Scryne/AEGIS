"""risk puanı anlık görüntüsü: risk_score_snapshot (RLS + saklama süresi)

Revision ID: 0007_risk_score_snapshot
Revises: 0006_ubo_computation
Create Date: 2026-10-31

Invariant 1 (CLAUDE.md, ADR-0002): ``risk_score_snapshot`` kiracıya-özel bir *veri* tablosudur →
``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu migration'ın
içindedir ve tablo kiracılar-arası izolasyon kapısına aynı değişiklikte eklenmiştir.

Invariant 4: ``retention_until`` doğuştan vardır — kayda geçmiş puan kararın kanıtıdır.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_risk_score_snapshot"
down_revision: str | None = "0006_ubo_computation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_score_snapshot",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(length=16), nullable=False),
        sa.Column("weights_version", sa.String(length=16), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
            name=op.f("fk_risk_score_snapshot_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_risk_score_snapshot_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_score_snapshot")),
    )
    op.create_index(op.f("ix_risk_score_snapshot_tenant_id"), "risk_score_snapshot", ["tenant_id"])
    op.create_index(op.f("ix_risk_score_snapshot_entity_id"), "risk_score_snapshot", ["entity_id"])
    op.create_index(
        op.f("ix_risk_score_snapshot_retention_until"), "risk_score_snapshot", ["retention_until"]
    )
    op.create_index(
        "ix_risk_score_snapshot_entity_id_created_at",
        "risk_score_snapshot",
        ["entity_id", "created_at"],
    )

    # Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001).
    op.execute("ALTER TABLE risk_score_snapshot ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_score_snapshot FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY risk_score_snapshot_tenant_isolation ON risk_score_snapshot "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS risk_score_snapshot_tenant_isolation ON risk_score_snapshot")
    op.drop_table("risk_score_snapshot")
