"""WhatsApp message template catalog - a local mirror of a tenant's WABA
templates (name/language/category/status/components), used by the new
`whatsapp.send_template` workflow node's picker.

Revision ID: 0012_whatsapp_templates
Revises: 0011_workflow_compiled_graph
Create Date: 2026-09-11

Tenant-scoped (TenantScopedMixin) - gets enable_tenant_rls, same as
`connector_access_requests`. `category`/`status` are native Postgres enum
types (matching `WhatsAppTemplateCategory`/`WhatsAppTemplateStatus`'s
`sqlalchemy.Enum` columns) - created explicitly before the table, the
same `postgresql.ENUM(...).create(bind, checkfirst=True)` pattern
`0006_templates_plans_access_reqs.py` already establishes for
`connector_access_request_status`.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

from fusionflow.db.rls import enable_tenant_rls, disable_tenant_rls

revision: str = "0012_whatsapp_templates"
down_revision: Union[str, None] = "0011_workflow_compiled_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORY_ENUM = postgresql.ENUM(
    "marketing", "utility", "authentication", name="whatsapp_template_category", create_type=False
)
STATUS_ENUM = postgresql.ENUM(
    "approved", "pending", "rejected", name="whatsapp_template_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    CATEGORY_ENUM.create(bind, checkfirst=True)
    STATUS_ENUM.create(bind, checkfirst=True)

    op.execute(
        """CREATE TABLE whatsapp_templates (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	connector_instance_id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	language VARCHAR(20) NOT NULL,
	category whatsapp_template_category NOT NULL,
	status whatsapp_template_status DEFAULT 'pending' NOT NULL,
	components JSONB DEFAULT '{}'::jsonb NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_whatsapp_template_instance_name_lang UNIQUE (connector_instance_id, name, language),
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""
    )
    op.execute("CREATE INDEX ix_whatsapp_templates_tenant_id ON whatsapp_templates (tenant_id)")
    op.execute("CREATE INDEX ix_whatsapp_templates_connector_instance_id ON whatsapp_templates (connector_instance_id)")

    enable_tenant_rls(op, "whatsapp_templates")


def downgrade() -> None:
    disable_tenant_rls(op, "whatsapp_templates")
    op.execute("DROP TABLE IF EXISTS whatsapp_templates CASCADE")
    bind = op.get_bind()
    STATUS_ENUM.drop(bind, checkfirst=True)
    CATEGORY_ENUM.drop(bind, checkfirst=True)
