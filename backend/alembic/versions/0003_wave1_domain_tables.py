"""Wave 1 domain schema: custom fields, catalog, fixed connectors,
connector framework, workflow engine, and super-admin tables.

Revision ID: 0003_wave1_domain_tables
Revises: 0002_rls_smoke_test
Create Date: 2026-09-09

Generated from `fusionflow.db.models` metadata (not hand-transcribed) to
guarantee the DDL matches the ORM models exactly - there was no live
Postgres available in the build environment to run
`alembic revision --autogenerate` against, so `CreateTable`/`CreateIndex`
were compiled directly from `Base.metadata` for the postgresql dialect
and embedded below as executed SQL, in the dependency order
`Base.metadata.sorted_tables` already resolved.

Two deferred cross-module foreign keys are added at the end, once every
table in this migration exists:
  * `payments.connector_instance_id` and `tickets.source_connector_instance_id`
    - both modules built these as plain UUID columns with no FK because
    `connector_instances` did not exist yet in their parallel build wave
    (see each model's docstring: "FK ... added in integration migration
    once connector framework lands").
  * `workflows.current_published_version_id` -> `workflow_versions.id`
    - declared `use_alter=True` in the model because `workflow_versions`
    references `workflows.id`, so the two tables cannot both be created
    with this FK inline without a circular dependency.

`workflow_triggers.connector_instance_id` and
`workflow_trigger_inbox.connector_instance_id` deliberately do NOT get a
FK here - per their model docstrings that is a permanent design choice
(validated in application code, not the database), not a temporary
parallel-wave gap like the two above.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0003_wave1_domain_tables"
down_revision: Union[str, None] = "0002_rls_smoke_test"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every Postgres ENUM type used by a Wave 1 table. Declared once here so
# upgrade()/downgrade() can create/drop them with the same checkfirst-safe
# pattern 0001_initial.py established.
ENUM_TYPES = {
    "connector_category": postgresql.ENUM('messaging', 'payment', 'calendar', 'mail', 'support_agent', 'dashboard', name="connector_category", create_type=False),
    "custom_field_entity_type": postgresql.ENUM('product', 'service', 'coupon', 'offer', name="custom_field_entity_type", create_type=False),
    "connector_state": postgresql.ENUM('not_connected', 'connecting', 'connected', 'action_required', 'error', 'disconnected', name="connector_state", create_type=False),
    "connector_health_status": postgresql.ENUM('healthy', 'degraded', 'down', name="connector_health_status", create_type=False),
    "coupon_discount_type": postgresql.ENUM('percentage', 'fixed_amount', name="coupon_discount_type", create_type=False),
    "custom_field_type": postgresql.ENUM('text', 'number', 'boolean', 'select', 'multiselect', 'date', 'richtext', name="custom_field_type", create_type=False),
    "kb_article_status": postgresql.ENUM('draft', 'published', name="kb_article_status", create_type=False),
    "product_service_type": postgresql.ENUM('product', 'service', name="product_service_type", create_type=False),
    "workflow_status": postgresql.ENUM('draft', 'published', 'archived', name="workflow_status", create_type=False),
    "connector_event_type": postgresql.ENUM('webhook_received', 'sync', 'oauth_callback', 'error', name="connector_event_type", create_type=False),
    "order_status": postgresql.ENUM('pending', 'paid', 'fulfilled', 'cancelled', name="order_status", create_type=False),
    "ticket_status": postgresql.ENUM('open', 'pending', 'resolved', 'closed', name="ticket_status", create_type=False),
    "workflow_validation_status": postgresql.ENUM('valid', 'invalid', name="workflow_validation_status", create_type=False),
    "payment_status": postgresql.ENUM('pending', 'succeeded', 'failed', 'refunded', name="payment_status", create_type=False),
    "ticket_message_author_type": postgresql.ENUM('customer', 'agent', 'system', 'support_agent_ai', name="ticket_message_author_type", create_type=False),
    "workflow_run_status": postgresql.ENUM('running', 'completed', 'failed', 'cancelled', name="workflow_run_status", create_type=False),
    "workflow_run_step_status": postgresql.ENUM('pending', 'running', 'succeeded', 'failed', 'skipped', name="workflow_run_step_status", create_type=False),
}

TABLES_IN_DEPENDENCY_ORDER = [
    "connector_types",
    "feature_flags",
    "field_templates",
    "audit_log",
    "connector_instances",
    "coupons",
    "customers",
    "feature_flag_overrides",
    "field_definitions",
    "impersonation_sessions",
    "kb_articles",
    "offers",
    "products_services",
    "workflow_trigger_inbox",
    "workflows",
    "connector_credentials",
    "connector_events",
    "connector_oauth_states",
    "orders",
    "tickets",
    "workflow_triggers",
    "workflow_versions",
    "payments",
    "ticket_messages",
    "workflow_runs",
    "workflow_run_steps",
]

RLS_TABLES = [
    "connector_instances",
    "connector_credentials",
    "connector_events",
    "connector_oauth_states",
    "field_definitions",
    "products_services",
    "coupons",
    "offers",
    "customers",
    "orders",
    "payments",
    "tickets",
    "ticket_messages",
    "kb_articles",
    "workflows",
    "workflow_versions",
    "workflow_runs",
    "workflow_run_steps",
    "workflow_triggers",
    "workflow_trigger_inbox",
]

CREATE_TABLE_SQL = {
    "connector_types": """CREATE TABLE connector_types (
	id UUID NOT NULL, 
	key VARCHAR(80) NOT NULL, 
	category connector_category NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	config_schema JSONB NOT NULL, 
	oauth BOOLEAN NOT NULL, 
	is_enabled_globally BOOLEAN DEFAULT 'true' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    "feature_flags": """CREATE TABLE feature_flags (
	id UUID NOT NULL, 
	key VARCHAR(120) NOT NULL, 
	description TEXT, 
	is_global_default BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    "field_templates": """CREATE TABLE field_templates (
	id UUID NOT NULL, 
	vertical VARCHAR(80) NOT NULL, 
	entity_type custom_field_entity_type NOT NULL, 
	is_global BOOLEAN DEFAULT 'true' NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	version INTEGER DEFAULT '1' NOT NULL, 
	fields JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)""",
    "audit_log": """CREATE TABLE audit_log (
	id UUID NOT NULL, 
	actor_user_id UUID, 
	actor_is_platform_admin BOOLEAN DEFAULT 'false' NOT NULL, 
	tenant_id UUID, 
	action VARCHAR(200) NOT NULL, 
	target_type VARCHAR(80), 
	target_id VARCHAR(200), 
	metadata JSONB, 
	ip_address VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE SET NULL
)""",
    "connector_instances": """CREATE TABLE connector_instances (
	id UUID NOT NULL, 
	connector_type_id UUID NOT NULL, 
	state connector_state DEFAULT 'not_connected' NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	connected_identity JSONB, 
	health_status connector_health_status, 
	last_webhook_at TIMESTAMP WITH TIME ZONE, 
	last_sync_at TIMESTAMP WITH TIME ZONE, 
	last_error_message TEXT, 
	provider_ref_ids JSONB, 
	disconnected_at TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connector_type_id) REFERENCES connector_types (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "coupons": """CREATE TABLE coupons (
	id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	discount_type coupon_discount_type NOT NULL, 
	discount_value NUMERIC(12, 2) NOT NULL, 
	valid_from TIMESTAMP WITH TIME ZONE, 
	valid_to TIMESTAMP WITH TIME ZONE, 
	usage_limit INTEGER, 
	custom_fields JSONB NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_coupon_tenant_code UNIQUE (tenant_id, code), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "customers": """CREATE TABLE customers (
	id UUID NOT NULL, 
	external_ref VARCHAR(200), 
	name VARCHAR(200) NOT NULL, 
	email VARCHAR(320), 
	phone VARCHAR(40), 
	custom_fields JSONB DEFAULT '{}' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "feature_flag_overrides": """CREATE TABLE feature_flag_overrides (
	id UUID NOT NULL, 
	feature_flag_id UUID NOT NULL, 
	tenant_id UUID, 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_feature_flag_override_flag_tenant UNIQUE (feature_flag_id, tenant_id), 
	FOREIGN KEY(feature_flag_id) REFERENCES feature_flags (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "field_definitions": """CREATE TABLE field_definitions (
	id UUID NOT NULL, 
	entity_type custom_field_entity_type NOT NULL, 
	key VARCHAR(100) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	field_type custom_field_type NOT NULL, 
	options JSONB, 
	required BOOLEAN DEFAULT 'false' NOT NULL, 
	sort_order INTEGER DEFAULT '0' NOT NULL, 
	source_template_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_field_definition_tenant_entity_key UNIQUE (tenant_id, entity_type, key), 
	FOREIGN KEY(source_template_id) REFERENCES field_templates (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "impersonation_sessions": """CREATE TABLE impersonation_sessions (
	id UUID NOT NULL, 
	platform_admin_user_id UUID NOT NULL, 
	target_user_id UUID NOT NULL, 
	target_business_id UUID NOT NULL, 
	reason TEXT NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	jwt_jti VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(platform_admin_user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_business_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "kb_articles": """CREATE TABLE kb_articles (
	id UUID NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	body TEXT NOT NULL, 
	tags VARCHAR[] DEFAULT '{}' NOT NULL, 
	status kb_article_status DEFAULT 'draft' NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "offers": """CREATE TABLE offers (
	id UUID NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	applies_to JSONB NOT NULL, 
	custom_fields JSONB NOT NULL, 
	active_from TIMESTAMP WITH TIME ZONE, 
	active_to TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "products_services": """CREATE TABLE products_services (
	id UUID NOT NULL, 
	entity_type product_service_type NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description VARCHAR(2000), 
	base_price NUMERIC(12, 2) NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	custom_fields JSONB NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflow_trigger_inbox": """CREATE TABLE workflow_trigger_inbox (
	id UUID NOT NULL, 
	event_type VARCHAR(150) NOT NULL, 
	payload JSONB NOT NULL, 
	connector_instance_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflows": """CREATE TABLE workflows (
	id UUID NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	status workflow_status DEFAULT 'draft' NOT NULL, 
	current_published_version_id UUID, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "connector_credentials": """CREATE TABLE connector_credentials (
	id UUID NOT NULL, 
	connector_instance_id UUID NOT NULL, 
	ciphertext BYTEA NOT NULL, 
	encryption_key_version INTEGER NOT NULL, 
	redacted_preview VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	rotated_at TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "connector_events": """CREATE TABLE connector_events (
	id UUID NOT NULL, 
	connector_instance_id UUID NOT NULL, 
	event_type connector_event_type NOT NULL, 
	payload JSONB NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "connector_oauth_states": """CREATE TABLE connector_oauth_states (
	id UUID NOT NULL, 
	connector_instance_id UUID, 
	state_token VARCHAR(128) NOT NULL, 
	redirect_context JSONB NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "orders": """CREATE TABLE orders (
	id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	status order_status DEFAULT 'pending' NOT NULL, 
	total_amount NUMERIC(12, 2) DEFAULT '0' NOT NULL, 
	currency VARCHAR(3) DEFAULT 'USD' NOT NULL, 
	line_items JSONB DEFAULT '[]' NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "tickets": """CREATE TABLE tickets (
	id UUID NOT NULL, 
	customer_id UUID, 
	subject VARCHAR(300) NOT NULL, 
	status ticket_status DEFAULT 'open' NOT NULL, 
	priority VARCHAR(20) DEFAULT 'medium' NOT NULL, 
	source_connector_instance_id UUID, 
	assigned_user_id UUID, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE SET NULL, 
	FOREIGN KEY(assigned_user_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflow_triggers": """CREATE TABLE workflow_triggers (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	trigger_type VARCHAR(150) NOT NULL, 
	connector_instance_id UUID, 
	config JSONB NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflow_versions": """CREATE TABLE workflow_versions (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	version_number INTEGER NOT NULL, 
	graph JSONB NOT NULL, 
	validation_status workflow_validation_status, 
	validation_errors JSONB, 
	published_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_version_number UNIQUE (workflow_id, version_number), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "payments": """CREATE TABLE payments (
	id UUID NOT NULL, 
	order_id UUID, 
	customer_id UUID NOT NULL, 
	connector_instance_id UUID, 
	provider_ref VARCHAR(200), 
	amount NUMERIC(12, 2) NOT NULL, 
	currency VARCHAR(3) DEFAULT 'USD' NOT NULL, 
	status payment_status DEFAULT 'pending' NOT NULL, 
	raw_event_ref VARCHAR(500), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL, 
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "ticket_messages": """CREATE TABLE ticket_messages (
	id UUID NOT NULL, 
	ticket_id UUID NOT NULL, 
	author_type ticket_message_author_type NOT NULL, 
	body TEXT NOT NULL, 
	attachments JSONB DEFAULT '[]' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflow_runs": """CREATE TABLE workflow_runs (
	id UUID NOT NULL, 
	workflow_id UUID NOT NULL, 
	workflow_version_id UUID NOT NULL, 
	trigger_event_ref VARCHAR(200), 
	status workflow_run_status DEFAULT 'running' NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	loop_guard_count INTEGER DEFAULT '0' NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES workflows (id) ON DELETE CASCADE, 
	FOREIGN KEY(workflow_version_id) REFERENCES workflow_versions (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "workflow_run_steps": """CREATE TABLE workflow_run_steps (
	id UUID NOT NULL, 
	workflow_run_id UUID NOT NULL, 
	node_id VARCHAR(100) NOT NULL, 
	node_type VARCHAR(150) NOT NULL, 
	status workflow_run_step_status DEFAULT 'pending' NOT NULL, 
	input JSONB, 
	output JSONB, 
	error TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	attempt INTEGER DEFAULT '1' NOT NULL, 
	tenant_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
}

CREATE_INDEX_SQL = [
    'CREATE UNIQUE INDEX ix_connector_types_key ON connector_types (key)',
    'CREATE UNIQUE INDEX ix_feature_flags_key ON feature_flags (key)',
    'CREATE INDEX ix_field_templates_entity_type ON field_templates (entity_type)',
    'CREATE INDEX ix_field_templates_vertical ON field_templates (vertical)',
    'CREATE INDEX ix_audit_log_tenant_id ON audit_log (tenant_id)',
    'CREATE INDEX ix_audit_log_target_id ON audit_log (target_id)',
    'CREATE INDEX ix_audit_log_target_type ON audit_log (target_type)',
    'CREATE INDEX ix_audit_log_actor_user_id ON audit_log (actor_user_id)',
    'CREATE INDEX ix_audit_log_created_at ON audit_log (created_at)',
    'CREATE INDEX ix_connector_instances_tenant_id ON connector_instances (tenant_id)',
    'CREATE INDEX ix_connector_instances_connector_type_id ON connector_instances (connector_type_id)',
    'CREATE INDEX ix_coupons_code ON coupons (code)',
    'CREATE INDEX ix_coupons_tenant_id ON coupons (tenant_id)',
    'CREATE INDEX ix_customers_email ON customers (email)',
    'CREATE INDEX ix_customers_external_ref ON customers (external_ref)',
    'CREATE INDEX ix_customers_tenant_id ON customers (tenant_id)',
    'CREATE INDEX ix_feature_flag_overrides_feature_flag_id ON feature_flag_overrides (feature_flag_id)',
    'CREATE INDEX ix_feature_flag_overrides_tenant_id ON feature_flag_overrides (tenant_id)',
    'CREATE INDEX ix_field_definitions_tenant_id ON field_definitions (tenant_id)',
    'CREATE INDEX ix_field_definitions_entity_type ON field_definitions (entity_type)',
    'CREATE INDEX ix_impersonation_sessions_jwt_jti ON impersonation_sessions (jwt_jti)',
    'CREATE INDEX ix_impersonation_sessions_target_business_id ON impersonation_sessions (target_business_id)',
    'CREATE INDEX ix_impersonation_sessions_platform_admin_user_id ON impersonation_sessions (platform_admin_user_id)',
    'CREATE INDEX ix_impersonation_sessions_target_user_id ON impersonation_sessions (target_user_id)',
    'CREATE INDEX ix_kb_articles_tenant_id ON kb_articles (tenant_id)',
    'CREATE INDEX ix_offers_tenant_id ON offers (tenant_id)',
    'CREATE INDEX ix_products_services_entity_type ON products_services (entity_type)',
    'CREATE INDEX ix_products_services_tenant_id ON products_services (tenant_id)',
    'CREATE INDEX ix_workflow_trigger_inbox_tenant_id ON workflow_trigger_inbox (tenant_id)',
    'CREATE INDEX ix_workflow_trigger_inbox_event_type ON workflow_trigger_inbox (event_type)',
    'CREATE INDEX ix_workflows_tenant_id ON workflows (tenant_id)',
    'CREATE INDEX ix_connector_credentials_tenant_id ON connector_credentials (tenant_id)',
    'CREATE UNIQUE INDEX ix_connector_credentials_connector_instance_id ON connector_credentials (connector_instance_id)',
    'CREATE INDEX ix_connector_events_tenant_id ON connector_events (tenant_id)',
    'CREATE INDEX ix_connector_events_occurred_at ON connector_events (occurred_at)',
    'CREATE INDEX ix_connector_events_connector_instance_id ON connector_events (connector_instance_id)',
    'CREATE UNIQUE INDEX ix_connector_oauth_states_state_token ON connector_oauth_states (state_token)',
    'CREATE INDEX ix_connector_oauth_states_connector_instance_id ON connector_oauth_states (connector_instance_id)',
    'CREATE INDEX ix_connector_oauth_states_tenant_id ON connector_oauth_states (tenant_id)',
    'CREATE INDEX ix_orders_customer_id ON orders (customer_id)',
    'CREATE INDEX ix_orders_tenant_id ON orders (tenant_id)',
    'CREATE INDEX ix_tickets_assigned_user_id ON tickets (assigned_user_id)',
    'CREATE INDEX ix_tickets_tenant_id ON tickets (tenant_id)',
    'CREATE INDEX ix_tickets_customer_id ON tickets (customer_id)',
    'CREATE INDEX ix_workflow_triggers_tenant_id ON workflow_triggers (tenant_id)',
    'CREATE INDEX ix_workflow_triggers_workflow_id ON workflow_triggers (workflow_id)',
    'CREATE INDEX ix_workflow_triggers_trigger_type ON workflow_triggers (trigger_type)',
    'CREATE INDEX ix_workflow_versions_tenant_id ON workflow_versions (tenant_id)',
    'CREATE INDEX ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)',
    'CREATE INDEX ix_payments_customer_id ON payments (customer_id)',
    'CREATE INDEX ix_payments_connector_instance_id ON payments (connector_instance_id)',
    'CREATE INDEX ix_payments_tenant_id ON payments (tenant_id)',
    'CREATE INDEX ix_payments_order_id ON payments (order_id)',
    'CREATE INDEX ix_payments_provider_ref ON payments (provider_ref)',
    'CREATE INDEX ix_ticket_messages_tenant_id ON ticket_messages (tenant_id)',
    'CREATE INDEX ix_ticket_messages_ticket_id ON ticket_messages (ticket_id)',
    'CREATE INDEX ix_workflow_runs_workflow_version_id ON workflow_runs (workflow_version_id)',
    'CREATE INDEX ix_workflow_runs_tenant_id ON workflow_runs (tenant_id)',
    'CREATE INDEX ix_workflow_runs_workflow_id ON workflow_runs (workflow_id)',
    'CREATE INDEX ix_workflow_run_steps_workflow_run_id ON workflow_run_steps (workflow_run_id)',
    'CREATE INDEX ix_workflow_run_steps_tenant_id ON workflow_run_steps (tenant_id)',
]

DEFERRED_FK_SQL = [
    "ALTER TABLE workflows ADD CONSTRAINT fk_workflows_current_published_version FOREIGN KEY (current_published_version_id) REFERENCES workflow_versions (id) ON DELETE SET NULL",
    "ALTER TABLE payments ADD CONSTRAINT fk_payments_connector_instance_id FOREIGN KEY (connector_instance_id) REFERENCES connector_instances (id) ON DELETE SET NULL",
    "ALTER TABLE tickets ADD CONSTRAINT fk_tickets_source_connector_instance_id FOREIGN KEY (source_connector_instance_id) REFERENCES connector_instances (id) ON DELETE SET NULL",
]

DEFERRED_FK_DROP_SQL = [
    "ALTER TABLE tickets DROP CONSTRAINT IF EXISTS fk_tickets_source_connector_instance_id",
    "ALTER TABLE payments DROP CONSTRAINT IF EXISTS fk_payments_connector_instance_id",
    "ALTER TABLE workflows DROP CONSTRAINT IF EXISTS fk_workflows_current_published_version",
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUM_TYPES.values():
        enum_type.create(bind, checkfirst=True)

    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        op.execute(CREATE_TABLE_SQL[table_name])

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    for stmt in DEFERRED_FK_SQL:
        op.execute(stmt)

    # One RLS policy per tenant-scoped table - same helper, same policy SQL,
    # every time (see db/rls.py). Global/platform tables (connector_types,
    # field_templates, audit_log, feature_flags, feature_flag_overrides,
    # impersonation_sessions) are deliberately excluded - see their model
    # docstrings.
    for table_name in RLS_TABLES:
        enable_tenant_rls(op, table_name)


def downgrade() -> None:
    for table_name in reversed(RLS_TABLES):
        disable_tenant_rls(op, table_name)

    for stmt in DEFERRED_FK_DROP_SQL:
        op.execute(stmt)

    for table_name in reversed(TABLES_IN_DEPENDENCY_ORDER):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    bind = op.get_bind()
    for enum_type in reversed(list(ENUM_TYPES.values())):
        enum_type.drop(bind, checkfirst=True)

