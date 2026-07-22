"""çekirdek şema (organization/user/membership) + ilk RLS'li veri tablosu (tenant_setting)

Revision ID: 0001_core_schema_rls
Revises:
Create Date: 2026-07-22

Invariant 1 (bkz. CLAUDE.md, ADR-0002): kiracıya-özel *veri* tabloları migration'ın ta
kendisinde ENABLE + FORCE ROW LEVEL SECURITY ve kiracı izolasyon politikasını alır.
organization/user_account/membership kimlik (kontrol düzlemi) tablolarıdır ve bilinçli
olarak RLS taşımaz (kayıt/giriş tenant bağlamı yokken çalışır).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_core_schema_rls"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Kimlik / kontrol düzlemi (RLS'siz) ───────────────────────────────────
    op.create_table(
        "organization",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization")),
        sa.UniqueConstraint("slug", name=op.f("uq_organization_slug")),
    )
    op.create_table(
        "user_account",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_account")),
        sa.UniqueConstraint("email", name=op.f("uq_user_account_email")),
    )
    op.create_table(
        "membership",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "OWNER",
                "COMPLIANCE_OFFICER",
                "ANALYST",
                "AUDITOR",
                name="role",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_membership_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_membership_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership")),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_organization"),
    )
    op.create_index(op.f("ix_membership_organization_id"), "membership", ["organization_id"])
    op.create_index(op.f("ix_membership_user_id"), "membership", ["user_id"])

    # ── İlk kiracıya-özel *veri* tablosu (RLS'li) ────────────────────────────
    op.create_table(
        "tenant_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            name=op.f("fk_tenant_setting_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_setting")),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_setting_tenant_id"),
    )
    op.create_index(op.f("ix_tenant_setting_tenant_id"), "tenant_setting", ["tenant_id"])

    # --- RLS: kiracı izolasyonu (tenant_setting kiracıya-özeldir; bkz. ADR-0002) ---
    # FORCE gereklidir: uygulama, ileride tablo sahibi rolüyle bağlanılsa dahi RLS
    # baypas edilmesin.
    _enable_tenant_rls("tenant_setting")


def _enable_tenant_rls(table: str) -> None:
    """Bir tabloda kiracı izolasyonu RLS'ini etkinleştirir (tekrar kullanılabilir kalıp).

    Politika ``NULLIF(current_setting('app.current_tenant', true), '')::uuid`` kullanır:
    bağlam hiç ayarlanmamışsa ``current_setting(..., true)`` NULL döner; ama aynı oturumda
    daha önce (transaction-local) ayarlanıp geri alındıysa GUC boş STRING'e (``''``)
    döner — ki ``''::uuid`` HATA verirdi. NULLIF ile boş string NULL'a çevrilir →
    ``tenant_id = NULL`` → hiçbir satır eşleşmez → nazik **fail-closed** (hata değil).
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_setting_tenant_isolation ON tenant_setting")
    op.drop_index(op.f("ix_tenant_setting_tenant_id"), table_name="tenant_setting")
    op.drop_table("tenant_setting")
    op.drop_index(op.f("ix_membership_user_id"), table_name="membership")
    op.drop_index(op.f("ix_membership_organization_id"), table_name="membership")
    op.drop_table("membership")
    op.drop_table("user_account")
    op.drop_table("organization")
