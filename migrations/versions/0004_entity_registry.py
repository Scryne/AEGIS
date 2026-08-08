"""varlık kütüğü: entity/entity_attribute/relationship, document/proposal, discrepancy

Revision ID: 0004_entity_registry
Revises: 0003_screening
Create Date: 2026-08-08

Invariant 1 (CLAUDE.md, ADR-0002): eklenen ALTI tablo da kiracıya-özel *veri*
tablosudur → ``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu
migration'ın içindedir ve altısı da kiracılar-arası izolasyon kapısına eklenmiştir.

``pg_trgm`` uzantısı varlık çözümlemesi (ER v1, Revizyon R4) için kurulur: bulanık ad
eşleştirmesi pgvector/embedding yerine trigram benzerliğiyle yapılır. Uzantı ayrıcalıklı
``aegis`` rolüyle (migration bağlantısı) kurulur; ``aegis_app`` yalnız kullanır.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_entity_registry"
down_revision: str | None = "0003_screening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = (
    "entity",
    "entity_attribute",
    "relationship",
    "document",
    "extraction_proposal",
    "discrepancy",
)


def _enable_tenant_rls(table: str) -> None:
    """Kiracı izolasyonu RLS kalıbı (ayrıntılı gerekçe: migration 0001)."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def _tenant_columns() -> list[sa.Column[object]]:
    """Her kiracı tablosunun ortak kuyruğu (id, tenant_id, zaman damgaları)."""
    return [
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
    ]


def upgrade() -> None:
    # Bulanık ad eşleştirmesi (ER v1) — R4: embedding yerine trigram.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── entity ───────────────────────────────────────────────────────────────
    op.create_table(
        "entity",
        sa.Column("schema_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("name_normalized", sa.String(length=512), nullable=False),
        sa.Column("name_ascii", sa.String(length=512), nullable=False),
        sa.Column("tax_number", sa.String(length=16), nullable=True),
        sa.Column("mersis_number", sa.String(length=24), nullable=True),
        sa.Column("lei_code", sa.String(length=20), nullable=True),
        sa.Column("trade_registry_number", sa.String(length=64), nullable=True),
        # TCKN: AES-256-GCM ile şifreli (ADR-0005) — DB'de Text ciphertext.
        sa.Column("national_id", sa.Text(), nullable=True),
        sa.Column("national_id_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("incorporation_date", sa.Date(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["entity.id"],
            name=op.f("fk_entity_merged_into_id_entity"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_entity_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity")),
        sa.UniqueConstraint("tenant_id", "tax_number", name="uq_entity_tenant_id_tax_number"),
        sa.UniqueConstraint("tenant_id", "mersis_number", name="uq_entity_tenant_id_mersis_number"),
        sa.UniqueConstraint("tenant_id", "lei_code", name="uq_entity_tenant_id_lei_code"),
        sa.UniqueConstraint(
            "tenant_id",
            "national_id_fingerprint",
            name="uq_entity_tenant_id_national_id_fingerprint",
        ),
    )
    op.create_index(op.f("ix_entity_tenant_id"), "entity", ["tenant_id"])
    op.create_index(op.f("ix_entity_name_ascii"), "entity", ["name_ascii"])
    op.create_index(op.f("ix_entity_status"), "entity", ["status"])
    op.create_index(op.f("ix_entity_retention_until"), "entity", ["retention_until"])
    op.create_index("ix_entity_tenant_id_schema_type", "entity", ["tenant_id", "schema_type"])
    # Trigram indeksi: `name_ascii % :query` benzerlik sorgusunu indeksten karşılar.
    op.execute(
        "CREATE INDEX ix_entity_name_ascii_trgm ON entity USING gin (name_ascii gin_trgm_ops)"
    )

    # ── document (entity'ye bağlı; entity_attribute buna bağlanacak) ─────────
    op.create_table(
        "document",
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "extraction_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_engine", sa.String(length=64), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_document_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_document_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint(
            "tenant_id", "entity_id", "sha256", name="uq_document_tenant_entity_sha"
        ),
    )
    op.create_index(op.f("ix_document_tenant_id"), "document", ["tenant_id"])
    op.create_index(op.f("ix_document_entity_id"), "document", ["entity_id"])
    op.create_index(op.f("ix_document_extraction_status"), "document", ["extraction_status"])
    op.create_index(op.f("ix_document_retention_until"), "document", ["retention_until"])
    op.create_index("ix_document_tenant_id_created_at", "document", ["tenant_id", "created_at"])

    # ── entity_attribute (provenans: her gözlem ayrı satır) ──────────────────
    op.create_table(
        "entity_attribute",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_entity_attribute_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_entity_attribute_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_entity_attribute_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_attribute")),
        sa.UniqueConstraint(
            "entity_id",
            "name",
            "value",
            "source_type",
            name="uq_entity_attribute_entity_id_name_value_source_type",
        ),
    )
    op.create_index(op.f("ix_entity_attribute_tenant_id"), "entity_attribute", ["tenant_id"])
    op.create_index(op.f("ix_entity_attribute_entity_id"), "entity_attribute", ["entity_id"])
    op.create_index(op.f("ix_entity_attribute_document_id"), "entity_attribute", ["document_id"])
    op.create_index("ix_entity_attribute_entity_id_name", "entity_attribute", ["entity_id", "name"])

    # ── relationship ─────────────────────────────────────────────────────────
    op.create_table(
        "relationship",
        sa.Column("source_entity_id", sa.Uuid(), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("rel_type", sa.String(length=24), nullable=False),
        sa.Column("role_title", sa.String(length=255), nullable=True),
        sa.Column("ownership_percent", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_relationship_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["entity.id"],
            name=op.f("fk_relationship_source_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["entity.id"],
            name=op.f("fk_relationship_target_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_relationship_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relationship")),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "rel_type",
            "role_title",
            name="uq_relationship_source_target_type_role",
        ),
    )
    op.create_index(op.f("ix_relationship_tenant_id"), "relationship", ["tenant_id"])
    op.create_index(op.f("ix_relationship_source_entity_id"), "relationship", ["source_entity_id"])
    op.create_index(op.f("ix_relationship_target_entity_id"), "relationship", ["target_entity_id"])
    op.create_index(
        "ix_relationship_tenant_id_target_entity_id",
        "relationship",
        ["tenant_id", "target_entity_id"],
    )

    # ── extraction_proposal ──────────────────────────────────────────────────
    op.create_table(
        "extraction_proposal",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("resulting_entity_id", sa.Uuid(), nullable=True),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_extraction_proposal_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_extraction_proposal_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_entity_id"],
            ["entity.id"],
            name=op.f("fk_extraction_proposal_resulting_entity_id_entity"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_extraction_proposal_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_proposal")),
    )
    op.create_index(op.f("ix_extraction_proposal_tenant_id"), "extraction_proposal", ["tenant_id"])
    op.create_index(
        op.f("ix_extraction_proposal_document_id"), "extraction_proposal", ["document_id"]
    )
    op.create_index(op.f("ix_extraction_proposal_entity_id"), "extraction_proposal", ["entity_id"])
    op.create_index(
        "ix_extraction_proposal_tenant_id_status", "extraction_proposal", ["tenant_id", "status"]
    )

    # ── discrepancy ──────────────────────────────────────────────────────────
    op.create_table(
        "discrepancy",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_name", sa.String(length=64), nullable=False),
        sa.Column("declared_value", sa.Text(), nullable=False),
        sa.Column("declared_source_ref", sa.String(length=1024), nullable=True),
        sa.Column("observed_value", sa.Text(), nullable=False),
        sa.Column("observed_source_type", sa.String(length=16), nullable=False),
        sa.Column("observed_source_ref", sa.String(length=1024), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_tenant_columns(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_discrepancy_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_discrepancy_entity_id_entity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_discrepancy_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discrepancy")),
        sa.UniqueConstraint(
            "entity_id",
            "attribute_name",
            "declared_value",
            "observed_value",
            name="uq_discrepancy_entity_attribute_values",
        ),
    )
    op.create_index(op.f("ix_discrepancy_tenant_id"), "discrepancy", ["tenant_id"])
    op.create_index(op.f("ix_discrepancy_entity_id"), "discrepancy", ["entity_id"])
    op.create_index("ix_discrepancy_tenant_id_status", "discrepancy", ["tenant_id", "status"])

    for table in RLS_TABLES:
        _enable_tenant_rls(table)

    # Tarama kayıtları artık kütüğe bağlanabilir (kolon 0003'te ayrılmıştı).
    op.create_foreign_key(
        op.f("fk_screening_entity_id_entity"),
        "screening",
        "entity",
        ["entity_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_screening_entity_id_entity"), "screening", type_="foreignkey")
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_table("discrepancy")
    op.drop_table("extraction_proposal")
    op.drop_table("relationship")
    op.drop_table("entity_attribute")
    op.drop_table("document")
    op.execute("DROP INDEX IF EXISTS ix_entity_name_ascii_trgm")
    op.drop_table("entity")
    # pg_trgm bilinçli olarak DÜŞÜRÜLMEZ: başka nesneler kullanıyor olabilir.
