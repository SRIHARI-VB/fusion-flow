"""Add `coupons.applies_to` - gives coupons the same "scope this to specific
services/products" capability offers already have via `offers.applies_to`
(see `modules/catalog/models.py::Offer.applies_to`'s docstring for the
shape/rationale). `NOT NULL ... DEFAULT '{}'` backfills every existing row
in one statement, same pattern as `0020_schedule_purpose`'s `workflows
.purpose` column add.

Revision ID: 0034_coupon_applies_to
Revises: 0033_workflow_channel
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0034_coupon_applies_to"
down_revision: Union[str, None] = "0033_workflow_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE coupons ADD COLUMN applies_to JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE coupons DROP COLUMN IF EXISTS applies_to")
