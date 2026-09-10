"""Pending-approval business status, feature-module connector category,
and businesses.denial_reason/reviewed_by/reviewed_at.

Revision ID: 0007_pending_approval_feature
Revises: 0006_templates_plans_access_reqs
Create Date: 2026-09-10

Adds two new `business_status` enum values (`pending_approval`, `denied`)
and one new `connector_category` enum value (`feature`) - see the plan's
"Unified Module/Connector Catalog & Approval-Gated Onboarding" section for
why: self-serve signup now requires admin approval before login works, and
fixed feature modules (products, orders, tickets, ...) join the same
connector_types catalog as WhatsApp/Razorpay, distinguished by this new
category value.

`ALTER TYPE ... ADD VALUE` cannot run inside the same transaction as other
statements that might use the new value (a Postgres restriction, not an
Alembic one) - `op.get_context().autocommit_block()` runs each one in its
own implicit transaction, outside this migration's normal transactional
block. The three new `businesses` columns are ordinary, fully-transactional
`ALTER TABLE ADD COLUMN` statements and stay in the normal block.

No backfill: every change here is additive. Existing `businesses` rows keep
their current `status` (`active`/`suspended`) untouched, existing
`connector_types` rows keep their current `category`. `downgrade()` cannot
remove enum values (Postgres does not support it) - it drops the three new
columns only and is documented as a partial/irreversible downgrade for the
enum additions, matching this repo's other additive-enum migrations.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_pending_approval_feature"
down_revision: Union[str, None] = "0006_templates_plans_access_reqs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUSINESSES_ALTER_SQL = [
    "ALTER TABLE businesses ADD COLUMN denial_reason TEXT",
    "ALTER TABLE businesses ADD COLUMN reviewed_by UUID REFERENCES users (id) ON DELETE SET NULL",
    "ALTER TABLE businesses ADD COLUMN reviewed_at TIMESTAMP WITH TIME ZONE",
]

BUSINESSES_ALTER_DROP_SQL = [
    "ALTER TABLE businesses DROP COLUMN reviewed_at",
    "ALTER TABLE businesses DROP COLUMN reviewed_by",
    "ALTER TABLE businesses DROP COLUMN denial_reason",
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE business_status ADD VALUE IF NOT EXISTS 'pending_approval'")
        op.execute("ALTER TYPE business_status ADD VALUE IF NOT EXISTS 'denied'")
        op.execute("ALTER TYPE connector_category ADD VALUE IF NOT EXISTS 'feature'")

    for stmt in BUSINESSES_ALTER_SQL:
        op.execute(stmt)


def downgrade() -> None:
    # Postgres cannot drop enum values - the two business_status additions
    # and the one connector_category addition are irreversible. Only the
    # three new businesses columns can be cleanly rolled back.
    for stmt in BUSINESSES_ALTER_DROP_SQL:
        op.execute(stmt)
