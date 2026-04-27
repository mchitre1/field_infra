"""add risk_rules table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("match", sa.JSON(), nullable=False),
        sa.Column("effect", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_rules_org_enabled_priority", "risk_rules", ["org_id", "enabled", "priority"])


def downgrade() -> None:
    op.drop_index("ix_risk_rules_org_enabled_priority", table_name="risk_rules")
    op.drop_table("risk_rules")
