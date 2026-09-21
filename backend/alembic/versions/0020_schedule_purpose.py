"""Recurring/scheduled bulk-messaging support: adds `workflows.purpose`
(the "workflow purpose" tag - "automation" | "broadcast" - that filters
which triggers appear in the builder's palette, see
`modules/workflows/engine/registry.py`'s `applicable_purposes` field and
`modules/workflows/service.py::list_node_types_with_templates`'s purpose
filter) and the new `workflow_schedules` table (`modules/workflows/models.py
::WorkflowSchedule`) that `engine/schedule_poller.py` polls for due
recurring/one-off bulk sends.

Revision ID: 0020_schedule_purpose
Revises: 0019_workflow_catalog_notes
Create Date: 2026-09-16
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0020_schedule_purpose"
down_revision: Union[str, None] = "0019_workflow_catalog_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `NOT NULL ... DEFAULT 'automation'` backfills every existing row in
    # one statement - safe pre-launch (no live tenant data) and also just
    # the right shape for a small, bounded enum-like column going forward.
    op.execute(
        "ALTER TABLE workflows ADD COLUMN purpose VARCHAR(20) NOT NULL DEFAULT 'automation'"
    )

    op.execute(
        """CREATE TABLE workflow_schedules (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	frequency VARCHAR(20) NOT NULL,
	run_at TIMESTAMP WITH TIME ZONE,
	time_of_day VARCHAR(5),
	weekdays JSONB,
	day_of_month INTEGER,
	timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL,
	recipient_source JSONB NOT NULL,
	next_run_at TIMESTAMP WITH TIME ZONE NOT NULL,
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	last_run_at TIMESTAMP WITH TIME ZONE,
	last_run_status VARCHAR(20),
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""
    )
    op.execute("CREATE INDEX ix_workflow_schedules_workflow_id ON workflow_schedules (workflow_id)")
    op.execute("CREATE INDEX ix_workflow_schedules_tenant_id ON workflow_schedules (tenant_id)")
    op.execute("CREATE INDEX ix_workflow_schedules_next_run_at ON workflow_schedules (next_run_at)")

    enable_tenant_rls(op, "workflow_schedules")


def downgrade() -> None:
    disable_tenant_rls(op, "workflow_schedules")
    op.execute("DROP TABLE IF EXISTS workflow_schedules CASCADE")
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS purpose")
