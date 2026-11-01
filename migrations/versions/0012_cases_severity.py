"""tam izleme + vaka yönetimi: alarm derecesi/yeniden puanlama, compliance_case, case_comment (RLS)

Revision ID: 0012_cases_severity
Revises: 0011_adverse_media
Create Date: 2026-11-01

Invariant 1 (CLAUDE.md, ADR-0002): ``compliance_case`` ve ``case_comment`` kiracıya-özel *veri*
tablolarıdır → ``tenant_id`` + ENABLE/FORCE ROW LEVEL SECURITY + izolasyon politikası bu
migration'ın içindedir; ikisi de kiracılar-arası izolasyon kapısına aynı değişiklikte eklendi.

``monitoring_alert.severity`` eski satırlarda boş kalır: FORCE RLS altında bağlamsız bir UPDATE
hiçbir satıra dokunmaz, bu yüzden geri doldurma yapılmaz; okuma tarafı dereceyi farktan
yeniden hesaplar (ADR-0014).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_cases_severity"
down_revision: str | None = "0011_adverse_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
)


def _ts(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {_POLICY}")


def upgrade() -> None:
    op.add_column("monitoring_alert", sa.Column("severity", sa.String(length=16), nullable=True))
    op.add_column(
        "monitoring_alert",
        sa.Column("reassessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(op.f("ix_monitoring_alert_severity"), "monitoring_alert", ["severity"])

    op.create_table(
        "compliance_case",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("source_alert_id", sa.Uuid(), nullable=True),
        sa.Column("source_screening_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'new'"), nullable=False),
        sa.Column("edd", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("edd_template_version", sa.String(length=32), nullable=True),
        sa.Column("edd_checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=True),
        sa.Column("opened_by_user_id", sa.Uuid(), nullable=True),
        _ts("due_at"),
        _ts("first_review_at"),
        _ts("escalated_at"),
        _ts("decided_at"),
        _ts("closed_at"),
        sa.Column("resolution", sa.Text(), nullable=True),
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
            name=op.f("fk_compliance_case_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("fk_compliance_case_entity_id_entity"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_alert_id"],
            ["monitoring_alert.id"],
            name=op.f("fk_compliance_case_source_alert_id_monitoring_alert"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_screening_id"],
            ["screening.id"],
            name=op.f("fk_compliance_case_source_screening_id_screening"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_case")),
        sa.UniqueConstraint("source_alert_id", name=op.f("uq_compliance_case_source_alert_id")),
    )
    for col in ("tenant_id", "entity_id", "status", "assignee_user_id"):
        op.create_index(op.f(f"ix_compliance_case_{col}"), "compliance_case", [col])
    op.create_index(
        "ix_compliance_case_tenant_id_status", "compliance_case", ["tenant_id", "status"]
    )
    _rls("compliance_case")

    op.create_table(
        "case_comment",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("author_role", sa.String(length=32), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization.id"],
            name=op.f("fk_case_comment_tenant_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["compliance_case.id"],
            name=op.f("fk_case_comment_case_id_compliance_case"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_comment")),
    )
    op.create_index(op.f("ix_case_comment_tenant_id"), "case_comment", ["tenant_id"])
    op.create_index(op.f("ix_case_comment_case_id"), "case_comment", ["case_id"])
    _rls("case_comment")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS case_comment_tenant_isolation ON case_comment")
    op.drop_table("case_comment")
    op.execute("DROP POLICY IF EXISTS compliance_case_tenant_isolation ON compliance_case")
    op.drop_table("compliance_case")
    op.drop_index(op.f("ix_monitoring_alert_severity"), table_name="monitoring_alert")
    op.drop_column("monitoring_alert", "reassessment")
    op.drop_column("monitoring_alert", "severity")
