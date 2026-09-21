"""`quick_replies` - channel-agnostic reusable text snippets for the inbox
compose box.

Revision ID: 0027_quick_replies
Revises: 0026_media_assets
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0027_quick_replies"
down_revision: Union[str, None] = "0026_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE quick_replies (
	id UUID NOT NULL,
	title VARCHAR(200) NOT NULL,
	body TEXT NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = ["CREATE INDEX ix_quick_replies_tenant_id ON quick_replies (tenant_id)"]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)
    enable_tenant_rls(op, "quick_replies")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quick_replies CASCADE")
