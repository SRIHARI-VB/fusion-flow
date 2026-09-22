"""Add `broadcast_campaigns.location_*` - optional WhatsApp-only location
attachment for a broadcast send.

Revision ID: 0032_campaign_location
Revises: 0031_campaign_media
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0032_campaign_location"
down_revision: Union[str, None] = "0031_campaign_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN location_latitude DOUBLE PRECISION")
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN location_longitude DOUBLE PRECISION")
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN location_name VARCHAR(200)")
    op.execute("ALTER TABLE broadcast_campaigns ADD COLUMN location_address VARCHAR(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN location_address")
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN location_name")
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN location_longitude")
    op.execute("ALTER TABLE broadcast_campaigns DROP COLUMN location_latitude")
