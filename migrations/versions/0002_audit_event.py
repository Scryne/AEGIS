"""append-only denetim izi (audit_event) + kiracı-başına hash zinciri

Revision ID: 0002_audit_event
Revises: 0001_core_schema_rls
Create Date: 2026-07-23

Invariant 2 (bkz. CLAUDE.md, ADR-0004): denetim izi değiştirilemezdir. Çift katmanlı
zorlama:
  1. ``aegis_app`` (uygulama rolü) tablodan UPDATE/DELETE yapamaz (REVOKE) — ki initdb
     tüm tablolara varsayılan UPDATE/DELETE veriyordu; burada bu tablo için geri alınır.
  2. Bir BEFORE UPDATE/DELETE trigger'ı, hangi rol olursa olsun mutasyonu RAISE ile
     reddeder (trigger'ı devre dışı bırakabilen bir DBA'ya karşı son savunma hash
     zinciridir; bkz. verify_chain).

audit_event kiracıya-özel bir *veri* tablosudur → ``tenant_id`` + ENABLE/FORCE RLS +
kiracı izolasyon politikası (Invariant 1) bu migration'ın içindedir.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_audit_event"
down_revision: str | None = "0001_core_schema_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=True),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_audit_event_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
        sa.UniqueConstraint("tenant_id", "seq", name="uq_audit_event_tenant_id_seq"),
    )
    op.create_index(op.f("ix_audit_event_tenant_id"), "audit_event", ["tenant_id"])

    # --- Invariant 1: kiracı izolasyonu (audit_event kiracıya-özeldir) ---
    op.execute("ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_event FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY audit_event_tenant_isolation ON audit_event "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )

    # --- Invariant 2 (katman 1): uygulama rolünden (aegis_app) UPDATE/DELETE geri al ---
    # Rol henüz yoksa (ör. testte migration'lar rol yaratılmadan koşar) no-op. Rol adı
    # sabittir (bkz. initdb/10-app-role.sql); string literal — kullanıcı girdisi değil.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aegis_app') THEN
                REVOKE UPDATE, DELETE ON audit_event FROM aegis_app;
            END IF;
        END
        $$;
        """
    )

    # --- Invariant 2 (katman 2): mutasyonu rolden bağımsız reddeden trigger ---
    op.execute(
        """
        CREATE FUNCTION audit_event_prevent_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event append-only: % reddedildi', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_event_no_update_delete "
        "BEFORE UPDATE OR DELETE ON audit_event "
        "FOR EACH ROW EXECUTE FUNCTION audit_event_prevent_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_update_delete ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_prevent_mutation()")
    op.execute("DROP POLICY IF EXISTS audit_event_tenant_isolation ON audit_event")
    op.drop_index(op.f("ix_audit_event_tenant_id"), table_name="audit_event")
    op.drop_table("audit_event")
