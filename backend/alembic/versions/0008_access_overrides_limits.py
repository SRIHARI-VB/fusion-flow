"""Connector access overrides (per-tenant revoke/grant) and resource-count
limits (plan defaults + tenant overrides).

Revision ID: 0008_access_overrides_limits
Revises: 0007_pending_approval_feature
Create Date: 2026-09-10

Generated from `fusionflow.db.models` metadata (not hand-transcribed),
same approach as prior migrations in this series, for the same reason: no
live Postgres was available to run `alembic revision --autogenerate`
against when these models were authored in this environment.

`connector_access_overrides` and `resource_limit_overrides` are the only
genuinely tenant-scoped tables here (TenantScopedMixin) and get
`enable_tenant_rls` - `plan_resource_limits` is a global admin-managed
catalog table (like `plan_feature_flags`), no RLS.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls, disable_tenant_rls

revision: str = "0008_access_overrides_limits"
down_revision: Union[str, None] = "0007_pending_approval_feature"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_IN_DEPENDENCY_ORDER = [
    "plan_resource_limits",
    "resource_limit_overrides",
    "connector_access_overrides",
]

CREATE_TABLE_SQL = {
    "plan_resource_limits": """CREATE TABLE plan_resource_limits (
	id UUID NOT NULL,
	plan_id UUID NOT NULL,
	connector_type_id UUID NOT NULL,
	max_count INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_plan_resource_limit UNIQUE (plan_id, connector_type_id),
	FOREIGN KEY(plan_id) REFERENCES plans (id) ON DELETE CASCADE,
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE CASCADE
)""",
    "resource_limit_overrides": """CREATE TABLE resource_limit_overrides (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	connector_type_id UUID NOT NULL,
	max_count INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_resource_limit_override_tenant_type UNIQUE (tenant_id, connector_type_id),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE,
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE CASCADE
)""",
    "connector_access_overrides": """CREATE TABLE connector_access_overrides (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	connector_type_id UUID NOT NULL,
	granted BOOLEAN NOT NULL,
	set_by UUID,
	reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_connector_access_override_tenant_type UNIQUE (tenant_id, connector_type_id),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE,
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE CASCADE,
	FOREIGN KEY(set_by) REFERENCES users (id) ON DELETE SET NULL
)""",
}

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_plan_resource_limits_plan_id ON plan_resource_limits (plan_id)",
    "CREATE INDEX ix_plan_resource_limits_connector_type_id ON plan_resource_limits (connector_type_id)",
    "CREATE INDEX ix_resource_limit_overrides_tenant_id ON resource_limit_overrides (tenant_id)",
    "CREATE INDEX ix_resource_limit_overrides_connector_type_id ON resource_limit_overrides (connector_type_id)",
    "CREATE INDEX ix_connector_access_overrides_tenant_id ON connector_access_overrides (tenant_id)",
    "CREATE INDEX ix_connector_access_overrides_connector_type_id ON connector_access_overrides (connector_type_id)",
]


def upgrade() -> None:
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        op.execute(CREATE_TABLE_SQL[table_name])

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    enable_tenant_rls(op, "resource_limit_overrides")
    enable_tenant_rls(op, "connector_access_overrides")


def downgrade() -> None:
    disable_tenant_rls(op, "connector_access_overrides")
    disable_tenant_rls(op, "resource_limit_overrides")

    for table_name in reversed(TABLES_IN_DEPENDENCY_ORDER):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
