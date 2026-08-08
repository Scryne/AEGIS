"""dosya raporu: report (RLS + saklama süresi + bütünlük özeti)

Revision ID: 0005_report
Revises: 0004_entity_registry
Create Date: 2026-08-08

Invariant 1 (CLAUDE.md, ADR-0002): ``report`` kiracıya-özel bir *veri* tablosudur →
``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu migration'ın
içindedir ve tablo kiracılar-arası izolasyon kapısına aynı değişiklikte eklenmiştir.

Invariant 4: ``retention_until`` doğuştan vardır (dışa aktarılmış dosya, yükümlülüğün
kanıtıdır) ve ``sha256`` bütünlük kanıtı olarak saklanır (ADR-0008).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_report"
down_revision: str | None = "0004_entity_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "report_type", sa.String(length=16), server_default=sa.text("'dossier'"), nullable=False
        ),
        sa.Column("report_format", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        # Donmuş risk özeti: sonradan eşik/veri kümesi değişse de rapor yeniden
        # yorumlanmaz (ADR-0006'daki duruşun raporlamadaki karşılığı).
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("risk_rationale", sa.String(length=1024), nullable=False),
        sa.Column(
            "risk_findings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "screening_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "dataset_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=True),
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
            name=op.f("fk_report_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_report_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report")),
    )
    op.create_index(op.f("ix_report_tenant_id"), "report", ["tenant_id"])
    op.create_index(op.f("ix_report_entity_id"), "report", ["entity_id"])
    op.create_index(op.f("ix_report_sha256"), "report", ["sha256"])
    op.create_index(op.f("ix_report_retention_until"), "report", ["retention_until"])
    op.create_index("ix_report_tenant_id_created_at", "report", ["tenant_id", "created_at"])
    op.create_index("ix_report_entity_id_created_at", "report", ["entity_id", "created_at"])

    # Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001).
    op.execute("ALTER TABLE report ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE report FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY report_tenant_isolation ON report "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS report_tenant_isolation ON report")
    op.drop_table("report")
