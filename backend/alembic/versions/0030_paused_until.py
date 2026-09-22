"""Add `conversations.automation_paused_until` - the Human Handoff
automation's optional SLA auto-resume timer.

Revision ID: 0030_paused_until
Revises: 0029_conv_automation_paused
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0030_paused_until"
down_revision: Union[str, None] = "0029_conv_automation_paused"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN automation_paused_until TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP COLUMN automation_paused_until")
