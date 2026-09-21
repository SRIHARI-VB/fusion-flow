"""`predefined_automations` - the wizard-facing record for a guided
automation instance.

Revision ID: 0024_predefined_automations
Revises: 0023_connector_cat_expansion
Create Date: 2026-09-21

Backs the new Communication-nav predefined-automation wizards (e.g.
Instagram comment automation, WhatsApp appointment booking) - each row
points at an ordinary `workflows` row whose `graph` was assembled
server-side from this row's `config` rather than hand-drawn on the canvas.
No new execution machinery: `workflows`/`workflow_versions`/
`workflow_triggers` are all pre-existing and untouched by this migration.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0024_predefined_automations"
down_revision: Union[str, None] = "0023_connector_cat_expansion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE predefined_automations (
	id UUID NOT NULL,
	connector_instance_id UUID NOT NULL,
	automation_type VARCHAR(100) NOT NULL,
	workflow_id UUID NOT NULL,
	config JSONB DEFAULT '{}' NOT NULL,
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_predefined_automations_workflow UNIQUE (workflow_id),
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE,
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_predefined_automations_tenant_id ON predefined_automations (tenant_id)",
    "CREATE INDEX ix_predefined_automations_connector_instance_id ON predefined_automations (connector_instance_id)",
    "CREATE INDEX ix_predefined_automations_automation_type ON predefined_automations (automation_type)",
]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)
    enable_tenant_rls(op, "predefined_automations")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS predefined_automations CASCADE")
