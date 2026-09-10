"""Adds `workflow_versions.compiled_graph` - the WorkflowNodeTemplate-
resolved graph a published version actually executes, kept separate from
`.graph` (the authored form, which may still reference template keys) so
editing a published workflow keeps showing its friendly template
identity. See `engine.template_resolution.resolve_node_templates`.

Revision ID: 0011_workflow_compiled_graph
Revises: 0010_workflow_node_templates
Create Date: 2026-09-10

Purely additive, nullable - existing published versions simply have
`compiled_graph = NULL`, and `outbox_poller.py` falls back to `.graph` in
that case, so no backfill is needed.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0011_workflow_compiled_graph"
down_revision: Union[str, None] = "0010_workflow_node_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_versions ADD COLUMN compiled_graph JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE workflow_versions DROP COLUMN IF EXISTS compiled_graph")
