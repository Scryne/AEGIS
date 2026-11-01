"""kullanim dokumu

Revision ID: 0016_usage_statement
Revises: 0015_match_eval_run
Create Date: 2026-11-01

``usage_statement`` kiracıya-özel veri tablosudur → ENABLE/FORCE RLS + politika bu dosyada,
izolasyon kapısında (Invariant 1). Dönem başına tek satır (tekillik kısıtı, ADR-0018).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_usage_statement"
down_revision: str | None = "0015_match_eval_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_statement",
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("included_queries", sa.Integer(), nullable=False),
        sa.Column("used_queries", sa.Integer(), nullable=False),
        sa.Column("overage_queries", sa.Integer(), nullable=False),
        sa.Column("monitored_entities", sa.Integer(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "closed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_usage_statement_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_statement")),
        sa.UniqueConstraint("tenant_id", "period_start", name=op.f("uq_usage_statement_tenant_id")),
    )
    op.create_index(
        op.f("ix_usage_statement_tenant_id"), "usage_statement", ["tenant_id"], unique=False
    )
    op.execute("ALTER TABLE usage_statement ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_statement FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY usage_statement_tenant_isolation ON usage_statement "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS usage_statement_tenant_isolation ON usage_statement")
    op.drop_index(op.f("ix_usage_statement_tenant_id"), table_name="usage_statement")
    op.drop_table("usage_statement")
