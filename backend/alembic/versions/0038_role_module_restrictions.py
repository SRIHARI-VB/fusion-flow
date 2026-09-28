"""`role_module_restrictions` - Owner/Admin's per-role (Member/Viewer)
module visibility restrictions within a tenant.

Revision ID: 0038_role_module_restrictions
Revises: 0037_clinic_queue
Create Date: 2026-09-28

Tenant-scoped (TenantScopedMixin), so it gets `enable_tenant_rls` like
`connector_access_overrides` in 0008. Reuses the existing `membership_role`
Postgres enum type (created in 0001_initial, `create_type=False` here)
rather than declaring a new one.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0038_role_module_restrictions"
down_revision: Union[str, None] = "0037_clinic_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE role_module_restrictions (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	connector_type_id UUID NOT NULL,
	role membership_role NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_role_module_restriction_tenant_type_role UNIQUE (tenant_id, connector_type_id, role),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE,
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE CASCADE
)"""
    )
    op.execute("CREATE INDEX ix_role_module_restrictions_tenant_id ON role_module_restrictions (tenant_id)")
    op.execute(
        "CREATE INDEX ix_role_module_restrictions_connector_type_id ON role_module_restrictions (connector_type_id)"
    )

    enable_tenant_rls(op, "role_module_restrictions")


def downgrade() -> None:
    disable_tenant_rls(op, "role_module_restrictions")
    op.execute("DROP TABLE IF EXISTS role_module_restrictions CASCADE")
