"""Add `conversations.automation_paused` - the "human handoff" predefined
automation's `inbox.pause_automation` node sets this; the outbox poller's
dispatch gate skips starting a new run for a conversation while it's true.

Revision ID: 0029_conv_automation_paused
Revises: 0028_inbox_conversations
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0029_conv_automation_paused"
down_revision: Union[str, None] = "0028_inbox_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE conversations ADD COLUMN automation_paused BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP COLUMN automation_paused")
