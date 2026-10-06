"""Persist conversation reset boundaries and the next-message fresh-start flag.

Revision ID: 0039_conversation_reset
Revises: 0038_role_module_restrictions
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_conversation_reset"
down_revision = "0038_role_module_restrictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive, with existing conversation RLS and permissions unchanged.
    op.add_column("conversations", sa.Column("flow_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column(
        "flow_reset_pending", sa.Boolean(), nullable=False, server_default=sa.text("false"),
    ))


def downgrade() -> None:
    op.drop_column("conversations", "flow_reset_pending")
    op.drop_column("conversations", "flow_reset_at")
