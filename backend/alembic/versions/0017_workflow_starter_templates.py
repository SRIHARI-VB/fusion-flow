"""Admin-managed starter workflow templates (composable-workflow-builder
redesign, Phase 6) - ready-to-use example graphs (WhatsApp ordering,
appointment booking) built entirely from the new composable node types, a
tenant can start a new workflow from.

Revision ID: 0017_workflow_starter_templates
Revises: 0016_business_objects
Create Date: 2026-09-11

Global admin-managed catalog table (like `workflow_node_templates`/
`business_templates`) - no RLS, every tenant reads the same active rows.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017_workflow_starter_templates"
down_revision: Union[str, None] = "0016_business_objects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE workflow_starter_templates (
	id UUID NOT NULL,
	key VARCHAR(120) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	category VARCHAR(80) DEFAULT 'General' NOT NULL,
	icon VARCHAR(80),
	graph_json JSONB NOT NULL,
	required_object_types JSONB,
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key)
)"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_starter_templates CASCADE")
