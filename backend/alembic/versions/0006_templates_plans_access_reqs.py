"""Business templates, plans, connector access requests, and
businesses.messaging_paused/business_template_id/plan_id.

Revision ID: 0006_templates_plans_access_reqs
Revises: 0005_payments_customer_nullable
Create Date: 2026-09-10

Generated from `fusionflow.db.models` metadata (not hand-transcribed),
same approach as 0003_wave1_domain_tables.py, for the same reason: no
live Postgres was available in the environment that built these models
to run `alembic revision --autogenerate` against.

`businesses` already exists (migration 0001) - this migration ALTERs it
to add `messaging_paused`, `business_template_id`, and `plan_id` rather
than creating it fresh, so those three ALTER statements are hand-written
below instead of generated, ordered after `plans`/`business_templates`
are created (their tables must exist before businesses' FK columns can
reference them).

`connector_access_requests` is the only genuinely tenant-scoped table
here (TenantScopedMixin) and gets enable_tenant_rls; plans/
business_templates/plan_feature_flags/business_template_connector_types
are global admin-managed catalog tables, matching field_templates/
feature_flags - no RLS policy, per their models docstrings.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

from fusionflow.db.rls import enable_tenant_rls, disable_tenant_rls

revision: str = "0006_templates_plans_access_reqs"
down_revision: Union[str, None] = "0005_payments_customer_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUM_TYPES = {
    "connector_access_request_status": postgresql.ENUM('pending', 'approved', 'denied', name="connector_access_request_status", create_type=False),
}

TABLES_IN_DEPENDENCY_ORDER = [
    "plans",
    "business_templates",
    "plan_feature_flags",
    "business_template_connector_types",
    "connector_access_requests",
]

CREATE_TABLE_SQL = {
    "plans": """CREATE TABLE plans (
	id UUID NOT NULL, 
	key VARCHAR(120) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	is_default BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    "business_templates": """CREATE TABLE business_templates (
	id UUID NOT NULL, 
	key VARCHAR(120) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	vertical VARCHAR(80), 
	plan_id UUID, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES plans (id) ON DELETE SET NULL
)""",
    "plan_feature_flags": """CREATE TABLE plan_feature_flags (
	id UUID NOT NULL, 
	plan_id UUID NOT NULL, 
	feature_flag_id UUID NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_plan_feature_flag UNIQUE (plan_id, feature_flag_id), 
	FOREIGN KEY(plan_id) REFERENCES plans (id) ON DELETE CASCADE, 
	FOREIGN KEY(feature_flag_id) REFERENCES feature_flags (id) ON DELETE CASCADE
)""",
    "business_template_connector_types": """CREATE TABLE business_template_connector_types (
	id UUID NOT NULL, 
	business_template_id UUID NOT NULL, 
	connector_type_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_business_template_connector_type UNIQUE (business_template_id, connector_type_id), 
	FOREIGN KEY(business_template_id) REFERENCES business_templates (id) ON DELETE CASCADE, 
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE CASCADE
)""",
    "connector_access_requests": """CREATE TABLE connector_access_requests (
	id UUID NOT NULL, 
	connector_type_id UUID NOT NULL, 
	status connector_access_request_status DEFAULT 'pending' NOT NULL, 
	requested_by UUID NOT NULL, 
	reason TEXT, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE RESTRICT, 
	FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
}

CREATE_INDEX_SQL = [
    'CREATE UNIQUE INDEX ix_plans_key ON plans (key)',
    'CREATE INDEX ix_business_templates_vertical ON business_templates (vertical)',
    'CREATE INDEX ix_business_templates_plan_id ON business_templates (plan_id)',
    'CREATE UNIQUE INDEX ix_business_templates_key ON business_templates (key)',
    'CREATE INDEX ix_plan_feature_flags_feature_flag_id ON plan_feature_flags (feature_flag_id)',
    'CREATE INDEX ix_plan_feature_flags_plan_id ON plan_feature_flags (plan_id)',
    'CREATE INDEX ix_business_template_connector_types_business_template_id ON business_template_connector_types (business_template_id)',
    'CREATE INDEX ix_business_template_connector_types_connector_type_id ON business_template_connector_types (connector_type_id)',
    'CREATE INDEX ix_connector_access_requests_tenant_id ON connector_access_requests (tenant_id)',
    'CREATE INDEX ix_connector_access_requests_connector_type_id ON connector_access_requests (connector_type_id)',
    'CREATE INDEX ix_connector_access_requests_created_at ON connector_access_requests (created_at)',
    'CREATE INDEX ix_connector_access_requests_requested_by ON connector_access_requests (requested_by)',
    'CREATE INDEX ix_connector_access_requests_status ON connector_access_requests (status)',
]

BUSINESSES_ALTER_SQL = [
    "ALTER TABLE businesses ADD COLUMN messaging_paused BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE businesses ADD COLUMN business_template_id UUID REFERENCES business_templates (id) ON DELETE SET NULL",
    "ALTER TABLE businesses ADD COLUMN plan_id UUID REFERENCES plans (id) ON DELETE SET NULL",
]

BUSINESSES_ALTER_DROP_SQL = [
    "ALTER TABLE businesses DROP COLUMN plan_id",
    "ALTER TABLE businesses DROP COLUMN business_template_id",
    "ALTER TABLE businesses DROP COLUMN messaging_paused",
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUM_TYPES.values():
        enum_type.create(bind, checkfirst=True)

    # plans, business_templates (in that order - the latter's plan_id FK
    # needs the former) before businesses' ALTER, then the two
    # plan/template-bundle join tables, then the tenant-scoped access
    # request table (its FK to businesses already works today, and it
    # does not depend on businesses' new columns).
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        op.execute(CREATE_TABLE_SQL[table_name])
        if table_name == "business_templates":
            for stmt in BUSINESSES_ALTER_SQL:
                op.execute(stmt)

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    enable_tenant_rls(op, "connector_access_requests")


def downgrade() -> None:
    disable_tenant_rls(op, "connector_access_requests")

    for stmt in BUSINESSES_ALTER_DROP_SQL:
        op.execute(stmt)

    for table_name in reversed(TABLES_IN_DEPENDENCY_ORDER):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    bind = op.get_bind()
    for enum_type in reversed(list(ENUM_TYPES.values())):
        enum_type.drop(bind, checkfirst=True)

