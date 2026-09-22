"""Add `workflows.channel_connector_type_key` - advisory "which channel is
this workflow for" tag chosen in the New Workflow wizard's new "channel"
step (`WorkflowsListPage.tsx`), shown as a colored badge on the workflows
list page. Sibling column to `workflows.purpose` (see `models.py::Workflow
.channel_connector_type_key`'s docstring), but nullable - `NULL` ("General"
/ no specific channel) is a legitimate value here, not just unset.

Revision ID: 0033_workflow_channel
Revises: 0032_campaign_location
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0033_workflow_channel"
down_revision: Union[str, None] = "0032_campaign_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflows ADD COLUMN channel_connector_type_key VARCHAR(50)")


def downgrade() -> None:
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS channel_connector_type_key")
