"""Custom Business Object module (composable-workflow-builder redesign,
Phase 2): `object_type_definitions`, `object_field_definitions`, and
`object_records` - lets a tenant define their own record types (e.g.
"Delivery", "Appointment") with their own fields, without any platform
code change. See `modules/business_objects/models.py`'s module docstring
for the design rationale.

Revision ID: 0016_business_objects
Revises: 0015_workflow_run_pause_resume
Create Date: 2026-09-11

`object_field_definitions.field_type` reuses the existing `custom_field_type`
Postgres enum (created in 0003_wave1_domain_tables.py for
`field_definitions.field_type`) rather than a duplicate enum type - both
tables share the exact same field-type vocabulary
(`modules.custom_fields.models.FieldType`), and
`modules.business_objects.service.validate_record_payload` reuses
`custom_fields.validation.validate_custom_fields` directly against
`ObjectFieldDefinition` rows (duck-typed, same attribute shape as
`FieldDefinition`) - no new enum type is created here.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0016_business_objects"
down_revision: Union[str, None] = "0015_workflow_run_pause_resume"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_IN_DEPENDENCY_ORDER = [
    "object_type_definitions",
    "object_field_definitions",
    "object_records",
]

CREATE_TABLE_SQL = {
    "object_type_definitions": """CREATE TABLE object_type_definitions (
	id UUID NOT NULL,
	key VARCHAR(80) NOT NULL,
	name VARCHAR(200) NOT NULL,
	icon VARCHAR(80),
	description VARCHAR(2000),
	is_active BOOLEAN DEFAULT 'true' NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_object_type_tenant_key UNIQUE (tenant_id, key),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "object_field_definitions": """CREATE TABLE object_field_definitions (
	id UUID NOT NULL,
	object_type_id UUID NOT NULL,
	key VARCHAR(100) NOT NULL,
	label VARCHAR(200) NOT NULL,
	field_type custom_field_type NOT NULL,
	options JSONB,
	required BOOLEAN DEFAULT 'false' NOT NULL,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_object_field_type_key UNIQUE (object_type_id, key),
	FOREIGN KEY(object_type_id) REFERENCES object_type_definitions (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "object_records": """CREATE TABLE object_records (
	id UUID NOT NULL,
	object_type_id UUID NOT NULL,
	payload JSONB NOT NULL,
	customer_id UUID,
	created_by_run_id UUID,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(object_type_id) REFERENCES object_type_definitions (id) ON DELETE CASCADE,
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
}

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_object_type_definitions_tenant_id ON object_type_definitions (tenant_id)",
    "CREATE INDEX ix_object_type_definitions_key ON object_type_definitions (key)",
    "CREATE INDEX ix_object_field_definitions_tenant_id ON object_field_definitions (tenant_id)",
    "CREATE INDEX ix_object_field_definitions_object_type_id ON object_field_definitions (object_type_id)",
    "CREATE INDEX ix_object_records_tenant_id ON object_records (tenant_id)",
    "CREATE INDEX ix_object_records_object_type_id ON object_records (object_type_id)",
    "CREATE INDEX ix_object_records_customer_id ON object_records (customer_id)",
]

RLS_TABLES = ["object_type_definitions", "object_field_definitions", "object_records"]


def upgrade() -> None:
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        op.execute(CREATE_TABLE_SQL[table_name])

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    for table_name in RLS_TABLES:
        enable_tenant_rls(op, table_name)


def downgrade() -> None:
    for table_name in reversed(RLS_TABLES):
        disable_tenant_rls(op, table_name)

    for table_name in reversed(TABLES_IN_DEPENDENCY_ORDER):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
