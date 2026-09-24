"""Add `offers.discount_type`/`offers.discount_value` - offers previously
had no way to carry a percentage/amount at all (only coupons did), so an
offer could never be shown with "how much" in a message or the admin UI.
Both nullable (unlike coupon's required pair) - a qualitative offer with
no numeric discount stays representable.

Revision ID: 0035_offer_discount
Revises: 0034_coupon_applies_to
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_offer_discount"
down_revision: Union[str, None] = "0034_coupon_applies_to"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "coupon_discount_type"


def upgrade() -> None:
    # The enum type already exists (created for coupons.discount_type) -
    # reuse it, don't CREATE TYPE again.
    op.add_column(
        "offers",
        sa.Column(
            "discount_type",
            sa.Enum("percentage", "fixed_amount", name=_ENUM_NAME, create_type=False),
            nullable=True,
        ),
    )
    op.add_column("offers", sa.Column("discount_value", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("offers", "discount_value")
    op.drop_column("offers", "discount_type")
