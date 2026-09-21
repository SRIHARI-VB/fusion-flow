"""`conversations`/`messages` - the Unified Inbox's cross-channel
conversation/message store.

Revision ID: 0028_inbox_conversations
Revises: 0027_quick_replies
Create Date: 2026-09-21

Provider-agnostic (see `modules/inbox/models.py`'s module docstring) -
one `Conversation` per (tenant, connector_instance, external contact),
`Message` rows hanging off it. Two new enum types
(`message_direction`/`message_sender_type`), each used by exactly one
column, created fresh here (unlike `custom_field_type`, no existing enum
to reuse).
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0028_inbox_conversations"
down_revision: Union[str, None] = "0027_quick_replies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_IN_DEPENDENCY_ORDER = ["conversations", "messages"]

CREATE_TABLE_SQL = {
    "conversations": """CREATE TABLE conversations (
	id UUID NOT NULL,
	connector_instance_id UUID NOT NULL,
	external_contact_id VARCHAR(200) NOT NULL,
	display_name VARCHAR(200),
	assigned_agent_id UUID,
	last_message_at TIMESTAMP WITH TIME ZONE,
	unread_count INTEGER DEFAULT '0' NOT NULL,
	tenant_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_conversation_tenant_instance_contact UNIQUE (tenant_id, connector_instance_id, external_contact_id),
	FOREIGN KEY(connector_instance_id) REFERENCES connector_instances (id) ON DELETE CASCADE,
	FOREIGN KEY(assigned_agent_id) REFERENCES users (id) ON DELETE SET NULL,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
    "messages": """CREATE TABLE messages (
	id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	direction message_direction NOT NULL,
	sender_type message_sender_type NOT NULL,
	content TEXT NOT NULL,
	external_message_id VARCHAR(200),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	read_at TIMESTAMP WITH TIME ZONE,
	tenant_id UUID NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)""",
}

CREATE_INDEX_SQL = [
    "CREATE INDEX ix_conversations_tenant_id ON conversations (tenant_id)",
    "CREATE INDEX ix_conversations_connector_instance_id ON conversations (connector_instance_id)",
    "CREATE INDEX ix_messages_tenant_id ON messages (tenant_id)",
    "CREATE INDEX ix_messages_conversation_id ON messages (conversation_id)",
]

RLS_TABLES = ["conversations", "messages"]


def upgrade() -> None:
    op.execute("CREATE TYPE message_direction AS ENUM ('inbound', 'outbound')")
    op.execute("CREATE TYPE message_sender_type AS ENUM ('customer', 'agent')")

    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        op.execute(CREATE_TABLE_SQL[table_name])

    for stmt in CREATE_INDEX_SQL:
        op.execute(stmt)

    for table_name in RLS_TABLES:
        enable_tenant_rls(op, table_name)


def downgrade() -> None:
    for table_name in reversed(RLS_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    op.execute("DROP TYPE IF EXISTS message_sender_type")
    op.execute("DROP TYPE IF EXISTS message_direction")
