"""Kiracı planı: organization.plan_code + plan_started_on (E2.6, ADR-0012)

Revision ID: 0010_org_plan
Revises: 0009_sib_draft
Create Date: 2026-11-01

``organization`` kontrol düzlemi tablosudur (RLS'siz, ADR-0002); plan alanı buraya girer ki
kayıt/giriş öncesi de okunabilsin. Mevcut kiracılar ``pilot`` ile başlar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_org_plan"
down_revision: str | None = "0009_sib_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization",
        sa.Column(
            "plan_code", sa.String(length=32), server_default=sa.text("'pilot'"), nullable=False
        ),
    )
    op.add_column("organization", sa.Column("plan_started_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_organization_plan_code",
        "organization",
        "plan_code IN ('pilot', 'standart', 'kurumsal')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organization_plan_code", "organization", type_="check")
    op.drop_column("organization", "plan_started_on")
    op.drop_column("organization", "plan_code")
