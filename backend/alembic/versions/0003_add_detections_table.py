"""add detections table and inspection detection fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inspections", sa.Column("detection_count", sa.Integer(), nullable=True))

    op.create_table(
        "detections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("frame_id", sa.Uuid(), nullable=False),
        sa.Column("detection_type", sa.String(length=64), nullable=False),
        sa.Column("class_name", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_xmin", sa.Float(), nullable=False),
        sa.Column("bbox_ymin", sa.Float(), nullable=False),
        sa.Column("bbox_xmax", sa.Float(), nullable=False),
        sa.Column("bbox_ymax", sa.Float(), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["frame_id"], ["frames.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detections_inspection_id", "detections", ["inspection_id"], unique=False)
    op.create_index("ix_detections_frame_id", "detections", ["frame_id"], unique=False)
    op.create_index("ix_detections_type", "detections", ["detection_type"], unique=False)
    op.create_index("ix_detections_class_name", "detections", ["class_name"], unique=False)
    op.create_index("ix_detections_confidence", "detections", ["confidence"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_detections_confidence", table_name="detections")
    op.drop_index("ix_detections_class_name", table_name="detections")
    op.drop_index("ix_detections_type", table_name="detections")
    op.drop_index("ix_detections_frame_id", table_name="detections")
    op.drop_index("ix_detections_inspection_id", table_name="detections")
    op.drop_table("detections")
    op.drop_column("inspections", "detection_count")
