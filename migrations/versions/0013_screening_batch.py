"""toplu tarama: screening_batch, screening_batch_row (RLS)

Revision ID: 0013_screening_batch
Revises: 0012_cases_severity
Create Date: 2026-11-01

Invariant 1 (CLAUDE.md, ADR-0002): iki tablo da kiracıya-özel *veri* tablosudur → ``tenant_id`` +
ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu dosyada; ikisi de izolasyon kapısında.
Satır tablosu TCKN taşımaz (CSV içe aktarımı TCKN sütununu reddeder, ADR-0015).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_screening_batch"
down_revision: str | None = "0012_cases_severity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "screening_batch",
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("column_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_role", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_screening_batch_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_batch")),
    )
    op.create_index(
        op.f("ix_screening_batch_retention_until"),
        "screening_batch",
        ["retention_until"],
        unique=False,
    )
    op.create_index(op.f("ix_screening_batch_status"), "screening_batch", ["status"], unique=False)
    op.create_index(
        op.f("ix_screening_batch_tenant_id"), "screening_batch", ["tenant_id"], unique=False
    )
    op.create_table(
        "screening_batch_row",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duplicate_of", sa.Integer(), nullable=True),
        sa.Column("resolution", sa.String(length=16), nullable=True),
        sa.Column("resolution_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("screening_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("flagged_count", sa.Integer(), nullable=True),
        sa.Column("sanction_hits", sa.Integer(), nullable=True),
        sa.Column("pep_hits", sa.Integer(), nullable=True),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("risk_rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["screening_batch.id"],
            name=op.f("fk_screening_batch_row_batch_id_screening_batch"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_screening_batch_row_entity_id_entity"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["screening_id"],
            ["screening.id"],
            name=op.f("fk_screening_batch_row_screening_id_screening"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_screening_batch_row_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_batch_row")),
        sa.UniqueConstraint("batch_id", "row_no", name=op.f("uq_screening_batch_row_batch_id")),
    )
    op.create_index(
        op.f("ix_screening_batch_row_batch_id"), "screening_batch_row", ["batch_id"], unique=False
    )
    op.create_index(
        "ix_screening_batch_row_batch_id_status",
        "screening_batch_row",
        ["batch_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screening_batch_row_tenant_id"), "screening_batch_row", ["tenant_id"], unique=False
    )
    for table in ("screening_batch", "screening_batch_row"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in ("screening_batch_row", "screening_batch"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index(op.f("ix_screening_batch_row_tenant_id"), table_name="screening_batch_row")
    op.drop_index("ix_screening_batch_row_batch_id_status", table_name="screening_batch_row")
    op.drop_index(op.f("ix_screening_batch_row_batch_id"), table_name="screening_batch_row")
    op.drop_table("screening_batch_row")
    op.drop_index(op.f("ix_screening_batch_tenant_id"), table_name="screening_batch")
    op.drop_index(op.f("ix_screening_batch_status"), table_name="screening_batch")
    op.drop_index(op.f("ix_screening_batch_retention_until"), table_name="screening_batch")
    op.drop_table("screening_batch")
