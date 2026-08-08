"""tarama servisi: screening + match_candidate (RLS'li) ve sanctions_dataset (RLS-muaf)

Revision ID: 0003_screening
Revises: 0002_audit_event
Create Date: 2026-08-08

Invariant 1 (CLAUDE.md, ADR-0002): ``screening`` ve ``match_candidate`` kiracıya-özel
*veri* tablolarıdır → ``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon
politikası bu migration'ın içindedir. Kiracılar-arası izolasyon testi aynı değişiklikte
bu iki tablo için de iddia eklenmiştir.

``sanctions_dataset`` bilinçli olarak RLS-muaftır: müşteri verisi değil, kamuya açık
yaptırım veri kümelerinin katalog meta'sıdır ve tüm kiracılar aynı motoru paylaşır
(gerekçe: ADR-0006).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_screening"
down_revision: str | None = "0002_audit_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str) -> None:
    """Kiracı izolasyonu RLS kalıbı (bkz. migration 0001'deki ayrıntılı gerekçe).

    ``NULLIF(...)``: bağlam hiç ayarlanmamışsa NULL, transaction-local ayarlanıp geri
    alındıysa boş string döner; ikisi de NULL'a çevrilerek nazik **fail-closed** olur.
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def upgrade() -> None:
    # ── Tarama koşusu (kiracıya-özel, RLS'li) ────────────────────────────────
    op.create_table(
        "screening",
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_name", sa.String(length=512), nullable=False),
        sa.Column("subject_normalized", sa.String(length=512), nullable=False),
        sa.Column("subject_country", sa.String(length=8), nullable=True),
        sa.Column(
            "subjects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column(
            "dataset_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column(
            "thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_screening_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening")),
    )
    op.create_index(op.f("ix_screening_tenant_id"), "screening", ["tenant_id"])
    op.create_index(op.f("ix_screening_entity_id"), "screening", ["entity_id"])
    op.create_index(op.f("ix_screening_status"), "screening", ["status"])
    op.create_index(op.f("ix_screening_retention_until"), "screening", ["retention_until"])
    op.create_index("ix_screening_tenant_id_created_at", "screening", ["tenant_id", "created_at"])

    # ── Aday eşleşme (kiracıya-özel, RLS'li) ─────────────────────────────────
    op.create_table(
        "match_candidate",
        sa.Column("screening_id", sa.Uuid(), nullable=False),
        sa.Column("subject_key", sa.String(length=64), nullable=False),
        sa.Column("subject_name", sa.String(length=512), nullable=False),
        sa.Column("subject_role", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("caption", sa.String(length=512), nullable=False),
        sa.Column("schema_type", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("engine_matched", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "datasets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "countries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("band", sa.String(length=16), nullable=False),
        sa.Column(
            "decision", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "decided_automatically",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["screening_id"],
            ["screening.id"],
            name=op.f("fk_match_candidate_screening_id_screening"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_match_candidate_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_candidate")),
        sa.UniqueConstraint(
            "screening_id",
            "subject_key",
            "external_id",
            name="uq_match_candidate_screening_id_subject_key_external_id",
        ),
    )
    op.create_index(op.f("ix_match_candidate_tenant_id"), "match_candidate", ["tenant_id"])
    op.create_index(op.f("ix_match_candidate_screening_id"), "match_candidate", ["screening_id"])
    op.create_index(op.f("ix_match_candidate_score"), "match_candidate", ["score"])
    op.create_index(
        "ix_match_candidate_tenant_id_decision", "match_candidate", ["tenant_id", "decision"]
    )

    _enable_tenant_rls("screening")
    _enable_tenant_rls("match_candidate")

    # ── Veri kümesi tazeliği (RLS-MUAF; gerekçe: modül/ADR-0006) ─────────────
    op.create_table(
        "sanctions_dataset",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("last_export_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_count", sa.BigInteger(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("name", name=op.f("pk_sanctions_dataset")),
    )
    op.create_index(
        op.f("ix_sanctions_dataset_last_export_at"), "sanctions_dataset", ["last_export_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sanctions_dataset_last_export_at"), table_name="sanctions_dataset")
    op.drop_table("sanctions_dataset")

    op.execute("DROP POLICY IF EXISTS match_candidate_tenant_isolation ON match_candidate")
    op.execute("DROP POLICY IF EXISTS screening_tenant_isolation ON screening")

    op.drop_index("ix_match_candidate_tenant_id_decision", table_name="match_candidate")
    op.drop_index(op.f("ix_match_candidate_score"), table_name="match_candidate")
    op.drop_index(op.f("ix_match_candidate_screening_id"), table_name="match_candidate")
    op.drop_index(op.f("ix_match_candidate_tenant_id"), table_name="match_candidate")
    op.drop_table("match_candidate")

    op.drop_index("ix_screening_tenant_id_created_at", table_name="screening")
    op.drop_index(op.f("ix_screening_retention_until"), table_name="screening")
    op.drop_index(op.f("ix_screening_status"), table_name="screening")
    op.drop_index(op.f("ix_screening_entity_id"), table_name="screening")
    op.drop_index(op.f("ix_screening_tenant_id"), table_name="screening")
    op.drop_table("screening")
