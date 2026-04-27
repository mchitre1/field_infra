"""add progression_metrics and inspection counter

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inspections",
        sa.Column("progression_metric_count", sa.Integer(), nullable=True),
    )

    op.create_table(
        "progression_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("baseline_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("target_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("alignment_pair_id", sa.Uuid(), nullable=True),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("metric_unit", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alignment_pair_id"], ["alignment_pairs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["baseline_inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_progression_metrics_asset_zone_target",
        "progression_metrics",
        ["asset_zone_id", "target_inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_progression_metrics_metric_target",
        "progression_metrics",
        ["metric_name", "target_inspection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_progression_metrics_metric_target", table_name="progression_metrics")
    op.drop_index("ix_progression_metrics_asset_zone_target", table_name="progression_metrics")
    op.drop_table("progression_metrics")
    op.drop_column("inspections", "progression_metric_count")
