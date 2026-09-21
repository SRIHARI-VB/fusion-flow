"""Optional `setup_notes` free-text column on `workflow_starter_templates`
and `workflow_components` - admin guidance for anything a tenant should do
before using a template/component that isn't a connector dependency or a
`required_object_types` entry (e.g. "populate your product catalog
first"). See `modules/admin/models.py`'s field docstrings.

Revision ID: 0019_workflow_catalog_notes
Revises: 0018_workflow_components
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0019_workflow_catalog_notes"
down_revision: Union[str, None] = "0018_workflow_components"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_starter_templates ADD COLUMN setup_notes TEXT")
    op.execute("ALTER TABLE workflow_components ADD COLUMN setup_notes TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE workflow_components DROP COLUMN setup_notes")
    op.execute("ALTER TABLE workflow_starter_templates DROP COLUMN setup_notes")
