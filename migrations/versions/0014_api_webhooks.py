"""api anahtari ve webhook

Revision ID: 0014_api_webhooks
Revises: 0013_screening_batch
Create Date: 2026-11-01

``api_key`` kimlik denetim düzlemi tablosudur (oturum öncesi önekle aranır) → RLS'siz, uygulama
kodunda kiracıya süzülür (ADR-0002 istisnası, ADR-0016). ``webhook_endpoint`` ve
``webhook_delivery`` kiracıya-özel veri tablolarıdır → ENABLE/FORCE RLS + politika bu dosyada,
ikisi de izolasyon kapısında (Invariant 1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_api_webhooks"
down_revision: str | None = "0013_screening_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_key",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_api_key_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_key")),
        sa.UniqueConstraint("prefix", name=op.f("uq_api_key_prefix")),
    )
    op.create_index(op.f("ix_api_key_tenant_id"), "api_key", ["tenant_id"], unique=False)
    op.create_table(
        "webhook_endpoint",
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("events", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
            name=op.f("fk_webhook_endpoint_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_endpoint")),
    )
    op.create_index(
        op.f("ix_webhook_endpoint_tenant_id"), "webhook_endpoint", ["tenant_id"], unique=False
    )
    op.create_table(
        "webhook_delivery",
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["webhook_endpoint.id"],
            name=op.f("fk_webhook_delivery_endpoint_id_webhook_endpoint"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_webhook_delivery_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_delivery")),
    )
    op.create_index(
        op.f("ix_webhook_delivery_endpoint_id"), "webhook_delivery", ["endpoint_id"], unique=False
    )
    op.create_index(
        "ix_webhook_delivery_status_next",
        "webhook_delivery",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_delivery_tenant_id"), "webhook_delivery", ["tenant_id"], unique=False
    )
    for table in ("webhook_endpoint", "webhook_delivery"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in ("webhook_delivery", "webhook_endpoint"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index(op.f("ix_webhook_delivery_tenant_id"), table_name="webhook_delivery")
    op.drop_index("ix_webhook_delivery_status_next", table_name="webhook_delivery")
    op.drop_index(op.f("ix_webhook_delivery_endpoint_id"), table_name="webhook_delivery")
    op.drop_table("webhook_delivery")
    op.drop_index(op.f("ix_webhook_endpoint_tenant_id"), table_name="webhook_endpoint")
    op.drop_table("webhook_endpoint")
    op.drop_index(op.f("ix_api_key_tenant_id"), table_name="api_key")
    op.drop_table("api_key")
