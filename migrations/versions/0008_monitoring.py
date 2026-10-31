"""izleme-lite: entity.monitored + monitoring_alert (RLS)

Revision ID: 0008_monitoring
Revises: 0007_risk_score_snapshot
Create Date: 2026-10-31

Invariant 1 (CLAUDE.md, ADR-0002): ``monitoring_alert`` kiracıya-özel bir *veri* tablosudur →
``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu migration'ın
içindedir ve tablo kiracılar-arası izolasyon kapısına aynı değişiklikte eklenmiştir.
``entity.monitored`` mevcut satırlarda ``false`` başlar (kimse kendiliğinden izlemeye alınmaz).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_monitoring"
down_revision: str | None = "0007_risk_score_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entity",
        sa.Column("monitored", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(op.f("ix_entity_monitored"), "entity", ["monitored"])

    op.create_table(
        "monitoring_alert",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("screening_id", sa.Uuid(), nullable=False),
        sa.Column("previous_screening_id", sa.Uuid(), nullable=True),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        sa.Column("acknowledged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledge_note", sa.Text(), nullable=True),
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
            name=op.f("fk_monitoring_alert_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"],
            ["screening.id"],
            name=op.f("fk_monitoring_alert_screening_id_screening"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_screening_id"],
            ["screening.id"],
            name=op.f("fk_monitoring_alert_previous_screening_id_screening"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_monitoring_alert_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitoring_alert")),
    )
    op.create_index(op.f("ix_monitoring_alert_tenant_id"), "monitoring_alert", ["tenant_id"])
    op.create_index(op.f("ix_monitoring_alert_entity_id"), "monitoring_alert", ["entity_id"])
    op.create_index(op.f("ix_monitoring_alert_status"), "monitoring_alert", ["status"])
    op.create_index(
        "ix_monitoring_alert_tenant_id_status", "monitoring_alert", ["tenant_id", "status"]
    )

    # Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001).
    op.execute("ALTER TABLE monitoring_alert ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE monitoring_alert FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY monitoring_alert_tenant_isolation ON monitoring_alert "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS monitoring_alert_tenant_isolation ON monitoring_alert")
    op.drop_table("monitoring_alert")
    op.drop_index(op.f("ix_entity_monitored"), table_name="entity")
    op.drop_column("entity", "monitored")
