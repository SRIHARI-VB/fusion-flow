"""`media_assets` - a catalog row over media already uploaded through an
existing connector upload endpoint (Cloudflare R2's
`/connectors/{instance_id}/media`).

Revision ID: 0026_media_assets
Revises: 0025_broadcast_campaigns
Create Date: 2026-09-21

Purely a listing/index layer - never drives storage or deletion of the
underlying object (see `modules/media_library/models.py`).
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0026_media_assets"
down_revision: Union[str, None] = "0025_broadcast_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE media_assets (
	id UUID NOT NULL,
	url VARCHAR(1000) NOT NULL,
	filename VARCHAR(300) NOT NULL,
	content_type VARCHAR(150) NOT NULL,
	size_bytes INTEGER NOT NULL,
	source VARCHAR(50) NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = ["CREATE INDEX ix_media_assets_tenant_id ON media_assets (tenant_id)"]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)
    enable_tenant_rls(op, "media_assets")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS media_assets CASCADE")
