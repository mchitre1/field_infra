"""add maintenance_recommendations and inspection recommendation_count

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inspections",
        sa.Column("recommendation_count", sa.Integer(), nullable=True),
    )
    op.create_table(
        "maintenance_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False),
        sa.Column("priority_label", sa.String(length=32), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("action_summary", sa.String(length=512), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("sla_target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_days_suggested", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["target_inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_recommendations_target",
        "maintenance_recommendations",
        ["target_inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_recommendations_zone_target",
        "maintenance_recommendations",
        ["asset_zone_id", "target_inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_recommendations_label_target",
        "maintenance_recommendations",
        ["priority_label", "target_inspection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_recommendations_label_target", table_name="maintenance_recommendations")
    op.drop_index("ix_maintenance_recommendations_zone_target", table_name="maintenance_recommendations")
    op.drop_index("ix_maintenance_recommendations_target", table_name="maintenance_recommendations")
    op.drop_table("maintenance_recommendations")
    op.drop_column("inspections", "recommendation_count")
