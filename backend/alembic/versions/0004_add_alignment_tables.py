"""add alignment and change event tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inspections", sa.Column("aligned_pair_count", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("change_event_count", sa.Integer(), nullable=True))

    op.add_column("detections", sa.Column("centroid_x", sa.Float(), nullable=True))
    op.add_column("detections", sa.Column("centroid_y", sa.Float(), nullable=True))
    op.add_column("detections", sa.Column("asset_zone_hint", sa.String(length=255), nullable=True))
    op.create_index("ix_detections_asset_zone_hint", "detections", ["asset_zone_hint"], unique=False)

    op.create_table(
        "alignment_pairs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("baseline_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("target_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_detection_id", sa.Uuid(), nullable=True),
        sa.Column("target_detection_id", sa.Uuid(), nullable=True),
        sa.Column("alignment_score", sa.Float(), nullable=False),
        sa.Column("change_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["baseline_inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_detection_id"], ["detections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_detection_id"], ["detections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alignment_pairs_asset_zone_id", "alignment_pairs", ["asset_zone_id"], unique=False)
    op.create_index(
        "ix_alignment_pairs_inspection_pair",
        "alignment_pairs",
        ["baseline_inspection_id", "target_inspection_id"],
        unique=False,
    )
    op.create_index("ix_alignment_pairs_change_type", "alignment_pairs", ["change_type"], unique=False)

    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_change_events_asset_zone_id", "change_events", ["asset_zone_id"], unique=False)
    op.create_index("ix_change_events_inspection_id", "change_events", ["inspection_id"], unique=False)
    op.create_index("ix_change_events_event_type", "change_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_change_events_event_type", table_name="change_events")
    op.drop_index("ix_change_events_inspection_id", table_name="change_events")
    op.drop_index("ix_change_events_asset_zone_id", table_name="change_events")
    op.drop_table("change_events")

    op.drop_index("ix_alignment_pairs_change_type", table_name="alignment_pairs")
    op.drop_index("ix_alignment_pairs_inspection_pair", table_name="alignment_pairs")
    op.drop_index("ix_alignment_pairs_asset_zone_id", table_name="alignment_pairs")
    op.drop_table("alignment_pairs")

    op.drop_index("ix_detections_asset_zone_hint", table_name="detections")
    op.drop_column("detections", "asset_zone_hint")
    op.drop_column("detections", "centroid_y")
    op.drop_column("detections", "centroid_x")

    op.drop_column("inspections", "change_event_count")
    op.drop_column("inspections", "aligned_pair_count")
