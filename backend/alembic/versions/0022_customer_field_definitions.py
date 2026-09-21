"""`customer_field_definitions` - customers' own field-definition table.

Revision ID: 0022_customer_field_definitions
Revises: 0021_connector_category_storage
Create Date: 2026-09-20

Closes the gap where `Customer.custom_fields` (added in
0003_wave1_domain_tables.py) had no schema to validate against: `EntityType`
(the enum `field_definitions` is keyed on) only ever covered
product/service/coupon/offer, so `customers` could never register into it.
Rather than widening that closed enum, this follows the pattern
`0016_business_objects.py` established for `object_field_definitions`: a
tenant-scoped table with the exact same column shape (now factored out as
`custom_fields.models.ModuleFieldDefinitionMixin`), reusing the existing
`custom_field_type` Postgres enum rather than creating a new one.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0022_customer_field_definitions"
down_revision: Union[str, None] = "0021_connector_category_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TABLE_SQL = """CREATE TABLE customer_field_definitions (
	id UUID NOT NULL,
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
	CONSTRAINT uq_customer_field_tenant_key UNIQUE (tenant_id, key),
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_customer_field_definitions_tenant_id ON customer_field_definitions (tenant_id)",
]


def upgrade() -> None:
    op.execute(CREATE_TABLE_SQL)

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    enable_tenant_rls(op, "customer_field_definitions")


def downgrade() -> None:
    disable_tenant_rls(op, "customer_field_definitions")
    op.execute("DROP TABLE IF EXISTS customer_field_definitions CASCADE")
