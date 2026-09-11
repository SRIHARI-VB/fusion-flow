"""Add required_connector_type_key to workflow_node_templates — Phase 7
Part A's entitlement-gating column mirroring NodeExecutor/TriggerDefinition's
new class attribute of the same name (see engine/registry.py). Nullable and
additive: existing rows default to NULL, meaning "inherit the base
executor's own requirement" (see
`workflows/service.py::list_node_types_with_templates`), zero behavior
change until the seed scripts backfill real values.

Revision ID: 0013_wf_node_tmpl_req_connector
Revises: 0012_whatsapp_templates
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_wf_node_tmpl_req_connector"
down_revision: Union[str, None] = "0012_whatsapp_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workflow_node_templates ADD COLUMN required_connector_type_key VARCHAR(80)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE workflow_node_templates DROP COLUMN IF EXISTS required_connector_type_key"
    )
