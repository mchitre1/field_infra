"""add outcome_feedbacks

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outcome_feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("org_scope", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("issue_key", sa.String(length=512), nullable=False),
        sa.Column("outcome_kind", sa.String(length=32), nullable=False),
        sa.Column("outcome_code", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("target_inspection_id", sa.Uuid(), nullable=True),
        sa.Column("issue_state_id", sa.Uuid(), nullable=True),
        sa.Column("issue_state_event_id", sa.Uuid(), nullable=True),
        sa.Column("primary_detection_id", sa.Uuid(), nullable=True),
        sa.Column("detection_refs", sa.JSON(), nullable=True),
        sa.Column("captured_priority_label", sa.String(length=32), nullable=True),
        sa.Column("captured_priority_score", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["target_inspection_id"], ["inspections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_state_id"], ["issue_states.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_state_event_id"], ["issue_state_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["primary_detection_id"], ["detections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outcome_feedbacks_org_scope", "outcome_feedbacks", ["org_scope"])
    op.create_index("ix_outcome_feedbacks_created_at", "outcome_feedbacks", ["created_at"])
    op.create_index("ix_outcome_feedbacks_org_created", "outcome_feedbacks", ["org_id", "created_at"])
    op.create_index("ix_outcome_feedbacks_target", "outcome_feedbacks", ["target_inspection_id"])
    op.create_index("ix_outcome_feedbacks_zone_issue", "outcome_feedbacks", ["asset_zone_id", "issue_key"])
    op.create_index("ix_outcome_feedbacks_primary_det", "outcome_feedbacks", ["primary_detection_id"])


def downgrade() -> None:
    op.drop_index("ix_outcome_feedbacks_org_scope", table_name="outcome_feedbacks")
    op.drop_index("ix_outcome_feedbacks_primary_det", table_name="outcome_feedbacks")
    op.drop_index("ix_outcome_feedbacks_zone_issue", table_name="outcome_feedbacks")
    op.drop_index("ix_outcome_feedbacks_target", table_name="outcome_feedbacks")
    op.drop_index("ix_outcome_feedbacks_org_created", table_name="outcome_feedbacks")
    op.drop_index("ix_outcome_feedbacks_created_at", table_name="outcome_feedbacks")
    op.drop_table("outcome_feedbacks")
