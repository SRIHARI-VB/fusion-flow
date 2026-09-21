"""New `connector_category` enum value: `storage`.

Revision ID: 0021_connector_category_storage
Revises: 0020_schedule_purpose
Create Date: 2026-09-16

Adds `storage` to the `connector_category` Postgres enum, for the new
tenant-owned Cloudflare R2 (S3-compatible) connector backing file uploads
for message media/template headers (see
`modules/connectors/cloudflare_r2/adapter.py`). Follows the same
`autocommit_block()` pattern `0007_pending_approval_feature.py` established
for the `feature` category value - `ALTER TYPE ... ADD VALUE` cannot run
inside a normal transactional block.

No backfill: purely additive, no existing `connector_types` row changes
category. `downgrade()` cannot remove an enum value (Postgres does not
support it) and is documented as a no-op, matching this repo's other
additive-enum migrations.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0021_connector_category_storage"
down_revision: Union[str, None] = "0020_schedule_purpose"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE connector_category ADD VALUE IF NOT EXISTS 'storage'")


def downgrade() -> None:
    # Postgres cannot drop enum values - irreversible, matching
    # 0007_pending_approval_feature.py's own documented precedent.
    pass
