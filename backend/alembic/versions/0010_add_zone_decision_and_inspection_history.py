"""add zone_decision_logs and inspection_history_events

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zone_decision_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("issue_key", sa.String(length=512), nullable=True),
        sa.Column("inspection_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("issue_state_event_id", sa.Uuid(), nullable=True),
        sa.Column("outcome_feedback_id", sa.Uuid(), nullable=True),
        sa.Column("maintenance_recommendation_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_state_event_id"], ["issue_state_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outcome_feedback_id"], ["outcome_feedbacks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["maintenance_recommendation_id"], ["maintenance_recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zone_decision_logs_zone_created", "zone_decision_logs", ["asset_zone_id", "created_at"])
    op.create_index("ix_zone_decision_logs_org_zone_created", "zone_decision_logs", ["org_id", "asset_zone_id", "created_at"])
    op.create_index("ix_zone_decision_logs_inspection_created", "zone_decision_logs", ["inspection_id", "created_at"])

    op.create_table(
        "inspection_history_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=64), nullable=False),
        sa.Column("to_status", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspection_history_inspection_created", "inspection_history_events", ["inspection_id", "created_at"])
    op.create_index("ix_inspection_history_created", "inspection_history_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_inspection_history_created", table_name="inspection_history_events")
    op.drop_index("ix_inspection_history_inspection_created", table_name="inspection_history_events")
    op.drop_table("inspection_history_events")
    op.drop_index("ix_zone_decision_logs_inspection_created", table_name="zone_decision_logs")
    op.drop_index("ix_zone_decision_logs_org_zone_created", table_name="zone_decision_logs")
    op.drop_index("ix_zone_decision_logs_zone_created", table_name="zone_decision_logs")
    op.drop_table("zone_decision_logs")
