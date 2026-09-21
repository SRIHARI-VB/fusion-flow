"""`broadcast_campaigns` - the tenant-facing record for a scheduled bulk
WhatsApp send.

Revision ID: 0025_broadcast_campaigns
Revises: 0024_predefined_automations
Create Date: 2026-09-21

Wraps the pre-existing `workflows`/`workflow_schedules` machinery - no new
execution engine, just a tenant-facing wrapper row (see
`modules/broadcast_campaigns/models.py`).
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0025_broadcast_campaigns"
down_revision: Union[str, None] = "0024_predefined_automations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE broadcast_campaigns (
	id UUID NOT NULL,
	connector_instance_id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	message_text TEXT NOT NULL,
	recipient_phone_numbers JSONB DEFAULT '[]' NOT NULL,
	workflow_id UUID NOT NULL,
	schedule_id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_broadcast_campaigns_workflow UNIQUE (workflow_id),
	CONSTRAINT uq_broadcast_campaigns_schedule UNIQUE (schedule_id),
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE,
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE,
	FOREIGN KEY(schedule_id) REFERENCES workflow_schedules (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_broadcast_campaigns_tenant_id ON broadcast_campaigns (tenant_id)",
    "CREATE INDEX ix_broadcast_campaigns_connector_instance_id ON broadcast_campaigns (connector_instance_id)",
]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)
    enable_tenant_rls(op, "broadcast_campaigns")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS broadcast_campaigns CASCADE")
