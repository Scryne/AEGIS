"""Olumsuz haber adayı: adverse_media_item (RLS) — E2.5 beta, ADR-0013

Revision ID: 0011_adverse_media
Revises: 0010_org_plan
Create Date: 2026-11-01

Invariant 1 (CLAUDE.md, ADR-0002): kiracıya-özel veri tablosu → ``tenant_id`` + ENABLE/FORCE
ROW LEVEL SECURITY + izolasyon politikası bu göçün içindedir ve tablo kiracılar-arası izolasyon
kapısına aynı değişiklikte eklenmiştir. Haber metni saklanmaz (başlık, kaynak, bağlantı, tarih).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_adverse_media"
down_revision: str | None = "0010_org_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adverse_media_item",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("query", sa.String(length=512), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column(
            "negative_terms",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'aday'"), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_adverse_media_item_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_adverse_media_item_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adverse_media_item")),
        sa.UniqueConstraint("tenant_id", "entity_id", "url_hash", name="uq_adverse_media_item_url"),
        sa.CheckConstraint(
            "status IN ('aday', 'ilgili', 'ilgisiz')", name="ck_adverse_media_item_status"
        ),
    )
    op.create_index(op.f("ix_adverse_media_item_tenant_id"), "adverse_media_item", ["tenant_id"])
    op.create_index(op.f("ix_adverse_media_item_entity_id"), "adverse_media_item", ["entity_id"])
    op.create_index(op.f("ix_adverse_media_item_status"), "adverse_media_item", ["status"])

    op.execute("ALTER TABLE adverse_media_item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE adverse_media_item FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY adverse_media_item_tenant_isolation ON adverse_media_item "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS adverse_media_item_tenant_isolation ON adverse_media_item")
    op.drop_table("adverse_media_item")
