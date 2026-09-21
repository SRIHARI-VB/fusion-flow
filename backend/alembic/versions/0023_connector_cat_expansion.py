"""New `connector_category` enum values: `social`, `video`, `spreadsheet`.

Revision ID: 0023_connector_cat_expansion
Revises: 0022_customer_field_definitions
Create Date: 2026-09-21

Adds three new connector categories for the Instagram, Google Meet, and
Google Sheets connectors respectively (Google Calendar/Gmail reuse the
existing `calendar`/`mail` categories). Follows
`0021_connector_category_storage.py`'s `autocommit_block()` pattern -
`ALTER TYPE ... ADD VALUE` cannot run inside a normal transactional block.

Revision id kept to <=32 chars (unlike this file's first draft,
`0023_connector_category_social_video_spreadsheet`, which broke `alembic
upgrade head` with `StringDataRightTruncationError` on the final `UPDATE
alembic_version` - that table's `version_num` column is `VARCHAR(32)`,
and every existing revision id in this repo is exactly at or under that
limit for the same reason).

No backfill: purely additive, no existing `connector_types` row changes
category. `downgrade()` cannot remove an enum value (Postgres does not
support it) and is documented as a no-op, matching this repo's other
additive-enum migrations.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023_connector_cat_expansion"
down_revision: Union[str, None] = "0022_customer_field_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE connector_category ADD VALUE IF NOT EXISTS 'social'")
        op.execute("ALTER TYPE connector_category ADD VALUE IF NOT EXISTS 'video'")
        op.execute("ALTER TYPE connector_category ADD VALUE IF NOT EXISTS 'spreadsheet'")


def downgrade() -> None:
    # Postgres cannot drop enum values - irreversible, matching
    # 0007_pending_approval_feature.py's own documented precedent.
    pass
