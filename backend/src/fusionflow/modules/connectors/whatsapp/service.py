"""WhatsApp template catalog service — CRUD plus a Meta sync.

Mirrors the plain CRUD shape used throughout this codebase's other
tenant-scoped catalogs (e.g. `modules.custom_fields.service`). Deliberately
framework-free (raises `ConnectorError`, not `HTTPException`) matching
`modules.connectors.service`'s own split between domain logic and HTTP
mapping.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors.service import ConnectorError, get_instance
from fusionflow.modules.connectors.whatsapp.models import (
    WhatsAppTemplate,
    WhatsAppTemplateCategory,
    WhatsAppTemplateStatus,
)


async def list_templates(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector_instance_id: uuid.UUID
) -> list[WhatsAppTemplate]:
    rows = await session.execute(
        select(WhatsAppTemplate)
        .where(
            WhatsAppTemplate.tenant_id == tenant_id,
            WhatsAppTemplate.connector_instance_id == connector_instance_id,
        )
        .order_by(WhatsAppTemplate.name)
    )
    return list(rows.scalars().all())


async def get_template(
    session: AsyncSession, *, tenant_id: uuid.UUID, template_id: uuid.UUID
) -> WhatsAppTemplate | None:
    template = await session.get(WhatsAppTemplate, template_id)
    if template is None or template.tenant_id != tenant_id:
        return None
    return template


async def create_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    name: str,
    language: str,
    category: WhatsAppTemplateCategory,
    status: WhatsAppTemplateStatus,
    components: dict[str, Any],
) -> WhatsAppTemplate:
    # Confirms the instance is a real, owned WhatsApp connector before
    # attaching a template to it - the same "resolve through the tenant-
    # scoped generic lookup first" discipline every other per-instance
    # write in this codebase follows.
    instance = await get_instance(session, tenant_id=tenant_id, instance_id=connector_instance_id)
    if instance is None:
        raise ConnectorError("Connector instance not found", status_code=404)

    existing = (
        await session.execute(
            select(WhatsAppTemplate).where(
                WhatsAppTemplate.connector_instance_id == connector_instance_id,
                WhatsAppTemplate.name == name,
                WhatsAppTemplate.language == language,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConnectorError(f"Template '{name}' ({language}) already exists for this connector", status_code=409)

    template = WhatsAppTemplate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_instance_id=connector_instance_id,
        name=name,
        language=language,
        category=category,
        status=status,
        components=components,
    )
    session.add(template)
    await session.flush()
    return template


async def update_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    template_id: uuid.UUID,
    category: WhatsAppTemplateCategory | None,
    status: WhatsAppTemplateStatus | None,
    components: dict[str, Any] | None,
) -> WhatsAppTemplate:
    template = await get_template(session, tenant_id=tenant_id, template_id=template_id)
    if template is None:
        raise ConnectorError("Template not found", status_code=404)
    if category is not None:
        template.category = category
    if status is not None:
        template.status = status
    if components is not None:
        template.components = components
    await session.flush()
    return template


async def delete_template(session: AsyncSession, *, tenant_id: uuid.UUID, template_id: uuid.UUID) -> None:
    template = await get_template(session, tenant_id=tenant_id, template_id=template_id)
    if template is None:
        raise ConnectorError("Template not found", status_code=404)
    await session.delete(template)
    await session.flush()


def _category_from_meta(raw: str | None) -> WhatsAppTemplateCategory:
    try:
        return WhatsAppTemplateCategory(str(raw or "").lower())
    except ValueError:
        return WhatsAppTemplateCategory.UTILITY  # conservative default for an unrecognized category string


def _status_from_meta(raw: str | None) -> WhatsAppTemplateStatus:
    try:
        return WhatsAppTemplateStatus(str(raw or "").lower())
    except ValueError:
        return WhatsAppTemplateStatus.PENDING


def _components_from_meta(raw_components: list[dict[str, Any]]) -> dict[str, Any]:
    """Reshapes Meta's flat `components` list (each `{"type": "BODY"|...}`)
    into the `{header?, body, footer?, buttons?}` shape
    `WhatsAppTemplate.components` and the send-node's variable-count
    derivation expect."""
    result: dict[str, Any] = {}
    for component in raw_components:
        kind = str(component.get("type", "")).upper()
        text = component.get("text", "")
        if kind == "BODY":
            variable_count = text.count("{{")
            result["body"] = {"text": text, "variable_count": variable_count}
        elif kind == "HEADER":
            result["header"] = {"format": component.get("format", "TEXT"), "text": text}
        elif kind == "FOOTER":
            result["footer"] = {"text": text}
        elif kind == "BUTTONS":
            result["buttons"] = component.get("buttons", [])
    return result


async def sync_from_meta(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector_instance_id: uuid.UUID
) -> list[WhatsAppTemplate]:
    """Pulls the WABA's templates via `WhatsAppAdapter.sync_templates` and
    upserts them into the local catalog by `(connector_instance_id, name,
    language)`. Never deletes a locally-known template that Meta's
    response no longer includes (a template can be paused/archived on
    Meta's side without us wanting to silently drop a tenant's own record
    of it) - purely additive/updating."""
    from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter

    instance = await get_instance(session, tenant_id=tenant_id, instance_id=connector_instance_id)
    if instance is None:
        raise ConnectorError("Connector instance not found", status_code=404)

    raw_templates = await whatsapp_adapter.sync_templates(instance=instance, session=session)

    existing_by_key = {
        (t.name, t.language): t for t in await list_templates(session, tenant_id=tenant_id, connector_instance_id=connector_instance_id)
    }
    synced: list[WhatsAppTemplate] = []
    for raw in raw_templates:
        name = raw.get("name")
        language = raw.get("language")
        if not name or not language:
            continue
        category = _category_from_meta(raw.get("category"))
        status = _status_from_meta(raw.get("status"))
        components = _components_from_meta(raw.get("components") or [])

        existing = existing_by_key.get((name, language))
        if existing is not None:
            existing.category = category
            existing.status = status
            existing.components = components
            synced.append(existing)
        else:
            template = WhatsAppTemplate(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                connector_instance_id=connector_instance_id,
                name=name,
                language=language,
                category=category,
                status=status,
                components=components,
            )
            session.add(template)
            synced.append(template)

    await session.flush()
    return synced
