"""eslesme kalitesi olcumu

Revision ID: 0015_match_eval_run
Revises: 0014_api_webhooks
Create Date: 2026-11-01

``match_eval_run`` kiracıya-özel veri tablosudur → ENABLE/FORCE RLS + politika bu dosyada,
izolasyon kapısında (Invariant 1). Etiketler ayrı tabloda değil: insan kararları
``match_candidate``da durur (ADR-0017).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_match_eval_run"
down_revision: str | None = "0014_api_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_eval_run",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_match_eval_run_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_eval_run")),
    )
    op.create_index(
        op.f("ix_match_eval_run_created_at"), "match_eval_run", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_match_eval_run_tenant_id"), "match_eval_run", ["tenant_id"], unique=False
    )
    op.execute("ALTER TABLE match_eval_run ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE match_eval_run FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY match_eval_run_tenant_isolation ON match_eval_run "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS match_eval_run_tenant_isolation ON match_eval_run")
    op.drop_index(op.f("ix_match_eval_run_tenant_id"), table_name="match_eval_run")
    op.drop_index(op.f("ix_match_eval_run_created_at"), table_name="match_eval_run")
    op.drop_table("match_eval_run")
