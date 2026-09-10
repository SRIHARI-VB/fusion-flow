"""WhatsApp message template catalog — a local mirror of the templates a
tenant's WABA has registered with Meta (approval itself always happens on
Meta's side; we cannot approve a template ourselves).

Kept in its own module (not `modules/connectors/models.py`) since it is
genuinely WhatsApp-specific, matching `whatsapp/adapter.py`/`config.py`'s
existing submodule boundary — the generic connector framework tables stay
provider-agnostic.

Populated two ways: manual entry (an admin/tenant user types in a
template they know is approved) or `service.sync_from_meta` (pulls the
real list via `WhatsAppAdapter.sync_templates`). Either way, this table is
what the `whatsapp.send_template` workflow node's config drawer reads to
build its template picker + per-variable fields — see
`modules/workflows/nodes/whatsapp_send_template.py`.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class WhatsAppTemplateCategory(str, enum.Enum):
    MARKETING = "marketing"
    UTILITY = "utility"
    AUTHENTICATION = "authentication"


class WhatsAppTemplateStatus(str, enum.Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class WhatsAppTemplate(Base, TenantScopedMixin, TimestampMixin):
    """One (connector_instance, name, language) template row.

    `category` is informational/for the picker UI only - it's a property
    of the template itself as assigned when Meta approved it, never a
    field the workflow author sets at send time (see
    `whatsapp_send_template.py`'s config, which only takes
    `template_name`/`language_code`/variables).

    `components` mirrors Meta's own template-components shape closely
    enough to derive the send-node's variable fields from it: a `body`
    entry with `{"text": "...", "variable_count": N}`, an optional
    `header` entry (`{"format": "TEXT"|"IMAGE"|..., "text"?}`), an
    optional `footer` (`{"text"}`), and an optional `buttons` list.
    """

    __tablename__ = "whatsapp_templates"
    __table_args__ = (
        UniqueConstraint("connector_instance_id", "name", "language", name="uq_whatsapp_template_instance_name_lang"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[WhatsAppTemplateCategory] = mapped_column(
        Enum(
            WhatsAppTemplateCategory,
            name="whatsapp_template_category",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    status: Mapped[WhatsAppTemplateStatus] = mapped_column(
        Enum(
            WhatsAppTemplateStatus,
            name="whatsapp_template_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=WhatsAppTemplateStatus.PENDING,
        server_default=WhatsAppTemplateStatus.PENDING.value,
    )
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
