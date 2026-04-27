"""add frames table and inspection frame fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inspections", sa.Column("frame_count", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("video_duration_ms", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("video_fps", sa.Float(), nullable=True))
    op.add_column("inspections", sa.Column("video_codec", sa.String(length=255), nullable=True))

    op.create_table(
        "frames",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("frame_timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("s3_bucket", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("capture_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("site_hint", sa.String(length=512), nullable=True),
        sa.Column("asset_hint", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inspection_id", "frame_index", name="uq_frames_inspection_frame"),
    )
    op.create_index("ix_frames_inspection_id", "frames", ["inspection_id"], unique=False)
    op.create_index("ix_frames_capture_timestamp", "frames", ["capture_timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_frames_capture_timestamp", table_name="frames")
    op.drop_index("ix_frames_inspection_id", table_name="frames")
    op.drop_table("frames")
    op.drop_column("inspections", "video_codec")
    op.drop_column("inspections", "video_fps")
    op.drop_column("inspections", "video_duration_ms")
    op.drop_column("inspections", "frame_count")
