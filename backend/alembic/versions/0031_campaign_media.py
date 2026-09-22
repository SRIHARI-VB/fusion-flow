"""Add `broadcast_campaigns.media_url`/`media_type` - optional media
attachment for a broadcast send.

Revision ID: 0031_campaign_media
Revises: 0030_paused_until
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0031_campaign_media"
down_revision: Union[str, None] = "0030_paused_until"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN media_url VARCHAR(2000)")
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN media_type VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN media_type")
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN media_url")
