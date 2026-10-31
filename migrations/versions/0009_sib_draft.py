"""ŞİB taslağı: sib_draft (RLS)

Revision ID: 0009_sib_draft
Revises: 0008_monitoring
Create Date: 2026-11-01

Invariant 1 (CLAUDE.md, ADR-0002): ``sib_draft`` kiracıya-özel bir *veri* tablosudur →
``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu migration'ın içindedir
ve tablo kiracılar-arası izolasyon kapısına aynı değişiklikte eklenmiştir. Form içeriği tek
şifreli kolondadır (ADR-0005); düz kolonlar kişisel veri taşımaz.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_sib_draft"
down_revision: str | None = "0008_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sib_draft",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("reference_no", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'taslak'"), nullable=False
        ),
        sa.Column("category", sa.String(length=8), nullable=True),
        sa.Column("form_encrypted", sa.Text(), nullable=False),
        sa.Column("skeleton_sha256", sa.String(length=64), nullable=False),
        sa.Column("guide_version", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("export_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_sib_draft_entity_id_entity"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_sib_draft_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sib_draft")),
        sa.UniqueConstraint("tenant_id", "reference_no", name=op.f("uq_sib_draft_tenant_id")),
    )
    op.create_index(op.f("ix_sib_draft_tenant_id"), "sib_draft", ["tenant_id"])
    op.create_index(op.f("ix_sib_draft_entity_id"), "sib_draft", ["entity_id"])
    op.create_index(op.f("ix_sib_draft_status"), "sib_draft", ["status"])
    op.create_index(op.f("ix_sib_draft_retention_until"), "sib_draft", ["retention_until"])

    # Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001).
    op.execute("ALTER TABLE sib_draft ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sib_draft FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY sib_draft_tenant_isolation ON sib_draft "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS sib_draft_tenant_isolation ON sib_draft")
    op.drop_table("sib_draft")
