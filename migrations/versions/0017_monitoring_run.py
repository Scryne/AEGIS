"""izleme kosusu ve alarm bildirimi

Revision ID: 0017_monitoring_run
Revises: 0016_usage_statement
Create Date: 2026-11-03

``monitoring_run`` kiracıya-özel veri tablosudur → ENABLE/FORCE RLS + politika bu dosyada,
izolasyon kapısında (Invariant 1). Taranamayan varlıklar burada kalır: gece koşusunun hatası
yalnız log satırı olmasın, uyum görevlisi ekranda görsün (ADR-0019).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_monitoring_run"
down_revision: str | None = "0016_usage_statement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_run",
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("checked", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("alerts", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("retried", sa.Integer(), nullable=False),
        sa.Column("failures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_monitoring_run_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitoring_run")),
    )
    op.create_index(
        "ix_monitoring_run_tenant_started",
        "monitoring_run",
        ["tenant_id", "started_at"],
        unique=False,
    )
    op.execute("ALTER TABLE monitoring_run ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE monitoring_run FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY monitoring_run_tenant_isolation ON monitoring_run "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )
    op.add_column(
        "monitoring_alert", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("monitoring_alert", "notified_at")
    op.execute("DROP POLICY IF EXISTS monitoring_run_tenant_isolation ON monitoring_run")
    op.drop_index("ix_monitoring_run_tenant_started", table_name="monitoring_run")
    op.drop_table("monitoring_run")
