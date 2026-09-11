"""Add source/created_by_workflow_run_id/payment_method to orders — Phase 8
Part C. Additive and nullable-or-defaulted: `source` defaults to
"checkout" for every existing row (real checkout flow, unaffected by this
phase); `created_by_workflow_run_id`/`payment_method` are nullable and only
ever populated by the new `orders_service.create_order_from_workflow`
path (a conversational WhatsApp ordering flow). No FK on
`created_by_workflow_run_id` - mirrors `payments.connector_instance_id`'s
established "no FK across parallel-wave modules" convention.

Revision ID: 0014_orders_workflow_origin
Revises: 0013_wf_node_tmpl_req_connector
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014_orders_workflow_origin"
down_revision: Union[str, None] = "0013_wf_node_tmpl_req_connector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'checkout'"
    )
    op.execute(
        "ALTER TABLE orders ADD COLUMN created_by_workflow_run_id UUID"
    )
    op.execute(
        "ALTER TABLE orders ADD COLUMN payment_method VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS payment_method")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS created_by_workflow_run_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS source")
