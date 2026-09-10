"""Make payments.customer_id nullable.

Revision ID: 0005_payments_customer_nullable
Revises: 0004_fix_rls_null_tenant_context
Create Date: 2026-09-10

A payment arriving via a provider webhook (razorpay/adapter.py's now-real
`handle_webhook` -> `payments.service.upsert_payment_from_provider`) has no
built-in way to resolve which of our `customers` rows it belongs to unless
our own id was embedded in the provider's `notes` field ahead of time - and
no "create a Razorpay payment request" flow exists yet to do that
embedding. Leaving `customer_id` null in that case is safer than guessing;
the manual `POST /payments` test route still accepts an explicit
`customer_id` when the caller has one.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_payments_customer_nullable"
down_revision: Union[str, None] = "0004_fix_rls_null_tenant_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE payments ALTER COLUMN customer_id DROP NOT NULL")


def downgrade() -> None:
    # Any existing NULL customer_id rows would violate re-adding NOT NULL;
    # this downgrade is only meant for a database with no such rows yet.
    op.execute("ALTER TABLE payments ALTER COLUMN customer_id SET NOT NULL")
