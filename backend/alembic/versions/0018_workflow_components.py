"""Workflow components (composable-workflow-builder redesign) - insertable
fragments of a workflow (a handful of nodes+edges) a tenant drops into a
workflow they're already editing, as opposed to `workflow_starter_templates`'
whole-new-workflow shape. Two sources, two tables:

- `workflow_components`: admin-curated, global (no RLS, same pattern as
  `workflow_starter_templates`) - every tenant sees the same active rows.
- `workflow_user_components`: a tenant's own saved selection of nodes
  (tenant-scoped, RLS-protected, same pattern as `object_type_definitions`).

See `modules/admin/models.py::WorkflowComponent` and
`modules/workflows/models.py::WorkflowUserComponent`'s docstrings for the
full design rationale.

Revision ID: 0018_workflow_components
Revises: 0017_workflow_starter_templates
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0018_workflow_components"
down_revision: Union[str, None] = "0017_workflow_starter_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE workflow_components (
	id UUID NOT NULL,
	key VARCHAR(120) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	category VARCHAR(80) DEFAULT 'General' NOT NULL,
	icon VARCHAR(80),
	graph_fragment JSONB NOT NULL,
	required_object_types JSONB,
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key)
)"""
    )

    op.execute(
        """CREATE TABLE workflow_user_components (
	id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	category VARCHAR(80) DEFAULT 'Custom',
	icon VARCHAR(80),
	graph_fragment JSONB NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""
    )
    op.execute("CREATE INDEX ix_workflow_user_components_tenant_id ON workflow_user_components (tenant_id)")

    enable_tenant_rls(op, "workflow_user_components")


def downgrade() -> None:
    disable_tenant_rls(op, "workflow_user_components")
    op.execute("DROP TABLE IF EXISTS workflow_user_components CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_components CASCADE")
