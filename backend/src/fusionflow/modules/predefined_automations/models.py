"""`PredefinedAutomation`: the wizard-facing record for one guided
automation instance (e.g. one Instagram post's comment-to-DM automation,
one WhatsApp appointment-booking configuration).

Deliberately thin: the actual trigger/condition/action logic lives in the
`Workflow`/`WorkflowVersion` this row points at (built by
`service.py::create_predefined_automation` from the registered
`automation_type`'s `build_graph` function - see `registry.py`) - this
table exists only so the frontend has something to list/edit/pause that
isn't a `Workflow` (which would imply canvas-editable), and so `config`
(the wizard's own structured answers, e.g. trigger keywords + toggle
states) is preserved verbatim for re-opening the wizard on edit, distinct
from the generated `graph` JSON a wizard never round-trips back into form
fields.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class PredefinedAutomation(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "predefined_automations"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Registry key (e.g. "instagram.comment_automation") - plain string,
    # not a DB enum, matching `Workflow.purpose`'s "just a few values, no
    # migration ceremony to add a new automation type" convention; the set
    # of valid values lives entirely in `registry.py`, in code, not in the
    # schema.
    automation_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # One-to-one with the generated Workflow - `unique=True` enforces the
    # "exactly one predefined automation owns this workflow" invariant.
    # `ondelete="CASCADE"` means deleting the underlying Workflow (e.g. via
    # the generic /workflows API, which this row's existence does nothing
    # to prevent) silently deletes this row too rather than leaving a
    # dangling reference - acceptable since a predefined automation with no
    # backing workflow has nothing left to configure anyway.
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # The wizard's own structured answers (trigger keywords, matching
    # method, toggle states, ...) - re-shown verbatim when the wizard is
    # reopened for editing. Never read by the workflow engine itself; only
    # `build_graph(config)` (registry.py) ever interprets it.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Pause without deleting - see `service.py::set_active`'s docstring
    # for exactly what pausing does to the underlying Workflow.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
