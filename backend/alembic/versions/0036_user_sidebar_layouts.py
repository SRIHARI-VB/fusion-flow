"""`user_sidebar_layouts` - per-user saved sidebar customization (group
order, custom groups, per-item placement, archive state).

Revision ID: 0036_user_sidebar_layouts
Revises: 0035_offer_discount
Create Date: 2026-09-25

Pure per-user UI personalization, not a tenant entitlement (those live in
`modules/connectors/`). `user_id` is unique - one layout per user - and is
the real lookup key; `tenant_id` is carried only so `TenantScopedMixin`'s
RLS policy can apply (see `fusionflow.db.rls.enable_tenant_rls`), matching
every other tenant-scoped table in this app. `layout` is nullable: NULL
means "no customization saved yet", not an error.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0036_user_sidebar_layouts"
down_revision: Union[str, None] = "0035_offer_discount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE user_sidebar_layouts (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	layout JSONB,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_user_sidebar_layouts_user_id UNIQUE (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_user_sidebar_layouts_tenant_id ON user_sidebar_layouts (tenant_id)",
]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)
    enable_tenant_rls(op, "user_sidebar_layouts")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_sidebar_layouts CASCADE")
