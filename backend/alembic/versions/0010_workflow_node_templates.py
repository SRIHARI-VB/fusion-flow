"""Admin-managed workflow node template catalog - the "new integration
without a deploy" half of Part D's extensibility layer (generic executors
+ this catalog).

Revision ID: 0010_workflow_node_templates
Revises: 0009_workflow_dedupe_key
Create Date: 2026-09-10

Global admin-managed catalog table (like `business_templates`/
`plan_feature_flags`) - no RLS, every tenant reads the same active rows.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_workflow_node_templates"
down_revision: Union[str, None] = "0009_workflow_dedupe_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE workflow_node_templates (
	id UUID NOT NULL,
	key VARCHAR(120) NOT NULL,
	label VARCHAR(200) NOT NULL,
	description TEXT,
	category VARCHAR(80) DEFAULT 'Integrations' NOT NULL,
	base_node_type VARCHAR(150) NOT NULL,
	icon VARCHAR(80),
	default_config JSONB DEFAULT '{}'::jsonb NOT NULL,
	config_schema_overrides JSONB,
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (key)
)"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_node_templates CASCADE")
