"""Workflow run pause/resume (Phase 8 Part A): a new `waiting` RunStatus
enum value plus six nullable `workflow_runs` columns holding the suspended
state (`waiting_node_id`, `waiting_connector_instance_id`,
`waiting_correlation_key`, `waiting_frontier`, `waiting_variables`,
`waiting_expires_at`) and a partial unique index enforcing "only one
paused conversation per customer per channel at a time"
(`(tenant_id, waiting_connector_instance_id, waiting_correlation_key)
WHERE status = 'waiting'`).

Revision ID: 0015_workflow_run_pause_resume
Revises: 0014_orders_workflow_origin
Create Date: 2026-09-11

`ALTER TYPE ... ADD VALUE` cannot run inside the same transaction as other
statements that might use the new value (a Postgres restriction, not an
Alembic one) - `op.get_context().autocommit_block()` runs it in its own
implicit transaction, outside this migration's normal transactional block,
mirroring `0007_pending_approval_feature.py`'s identical need for a
different enum. The six new columns and the partial index are ordinary,
fully-transactional statements and stay in the normal block.

No backfill: purely additive. Existing `workflow_runs` rows keep their
current `status` and get `waiting_* = NULL`, which the partial index never
constrains. `downgrade()` cannot remove the enum value (Postgres does not
support it) - it drops the index and the six columns only, matching this
repo's other additive-enum migrations' documented partial/irreversible
downgrade.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0015_workflow_run_pause_resume"
down_revision: Union[str, None] = "0014_orders_workflow_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADD_COLUMNS_SQL = [
    "ALTER TABLE workflow_runs ADD COLUMN waiting_node_id VARCHAR(100)",
    "ALTER TABLE workflow_runs ADD COLUMN waiting_connector_instance_id UUID",
    "ALTER TABLE workflow_runs ADD COLUMN waiting_correlation_key VARCHAR(200)",
    "ALTER TABLE workflow_runs ADD COLUMN waiting_frontier JSONB",
    "ALTER TABLE workflow_runs ADD COLUMN waiting_variables JSONB",
    "ALTER TABLE workflow_runs ADD COLUMN waiting_expires_at TIMESTAMP WITH TIME ZONE",
]

DROP_COLUMNS_SQL = [
    "ALTER TABLE workflow_runs DROP COLUMN waiting_expires_at",
    "ALTER TABLE workflow_runs DROP COLUMN waiting_variables",
    "ALTER TABLE workflow_runs DROP COLUMN waiting_frontier",
    "ALTER TABLE workflow_runs DROP COLUMN waiting_correlation_key",
    "ALTER TABLE workflow_runs DROP COLUMN waiting_connector_instance_id",
    "ALTER TABLE workflow_runs DROP COLUMN waiting_node_id",
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE workflow_run_status ADD VALUE IF NOT EXISTS 'waiting'")

    for stmt in ADD_COLUMNS_SQL:
        op.execute(stmt)

    op.execute(
        "CREATE UNIQUE INDEX uq_workflow_runs_waiting_correlation "
        "ON workflow_runs (tenant_id, waiting_connector_instance_id, waiting_correlation_key) "
        "WHERE status = 'waiting'"
    )


def downgrade() -> None:
    # Postgres cannot drop enum values - the 'waiting' addition to
    # workflow_run_status is irreversible. Only the index and the six new
    # columns can be cleanly rolled back.
    op.execute("DROP INDEX IF EXISTS uq_workflow_runs_waiting_correlation")
    for stmt in DROP_COLUMNS_SQL:
        op.execute(stmt)
