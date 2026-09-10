"""Workflow trigger inbox idempotency: a nullable `dedupe_key` column plus
a partial unique index on (tenant_id, dedupe_key) so a redelivered webhook
can never create a second inbox row (and thus a second `WorkflowRun`) for
the same provider event.

Revision ID: 0009_workflow_dedupe_key
Revises: 0008_access_overrides_limits
Create Date: 2026-09-10

Part of Phase 4 ("Advanced Workflow Engine: Containers + Stability
Hardening") Part A - stability hardening. Purely additive: existing rows
get `dedupe_key = NULL`, which the partial index (`WHERE dedupe_key IS NOT
NULL`) never constrains, so this ships with zero backfill and zero risk to
existing inbox rows.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_workflow_dedupe_key"
down_revision: Union[str, None] = "0008_access_overrides_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_trigger_inbox ADD COLUMN dedupe_key VARCHAR(255)")
    op.execute(
        "CREATE UNIQUE INDEX uq_workflow_trigger_inbox_tenant_dedupe_key "
        "ON workflow_trigger_inbox (tenant_id, dedupe_key) "
        "WHERE dedupe_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_workflow_trigger_inbox_tenant_dedupe_key")
    op.execute("ALTER TABLE workflow_trigger_inbox DROP COLUMN IF EXISTS dedupe_key")
