"""add issue_states and issue_state_events

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issue_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_scope", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("asset_zone_id", sa.String(length=255), nullable=False),
        sa.Column("issue_key", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("last_target_inspection_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["last_target_inspection_id"], ["inspections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_scope", "asset_zone_id", "issue_key", name="uq_issue_states_identity"),
    )
    op.create_index("ix_issue_states_asset_zone", "issue_states", ["asset_zone_id"])
    op.create_index("ix_issue_states_state", "issue_states", ["state"])
    op.create_index("ix_issue_states_org_scope_zone", "issue_states", ["org_scope", "asset_zone_id"])

    op.create_table(
        "issue_state_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issue_state_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["issue_state_id"], ["issue_states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_state_events_issue", "issue_state_events", ["issue_state_id"])


def downgrade() -> None:
    op.drop_index("ix_issue_state_events_issue", table_name="issue_state_events")
    op.drop_table("issue_state_events")
    op.drop_index("ix_issue_states_org_scope_zone", table_name="issue_states")
    op.drop_index("ix_issue_states_state", table_name="issue_states")
    op.drop_index("ix_issue_states_asset_zone", table_name="issue_states")
    op.drop_table("issue_states")
