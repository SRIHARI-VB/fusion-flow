"""Record quarantined workflow inbox failures without replaying their sends.

Revision ID: 0040_inbox_processing_error
Revises: 0039_conversation_reset
"""

from alembic import op
import sqlalchemy as sa

revision = "0040_inbox_processing_error"
down_revision = "0039_conversation_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_trigger_inbox", sa.Column("processing_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_trigger_inbox", "processing_error")
