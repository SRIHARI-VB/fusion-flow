"""Shared helper for the `whatsapp.send_*` node family - every one of them
starts by resolving `config.connector_instance_id` into a real, tenant-
owned `ConnectorInstance` the same way, so this factors that out instead
of repeating the same `uuid.UUID(...)` + `get_instance` + not-found dance
six times (`send_whatsapp_message.py`, predating this file, still has its
own inline copy - not retrofitted, matching this codebase's established
"don't touch already-tested code for no functional gain" convention).

Leading underscore: this is a private implementation-sharing module
within `modules/workflows/nodes/`, not itself a node type - never
imported by `nodes/__init__.py`'s registration list.
"""

from __future__ import annotations

import uuid

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import ConnectorInstance
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure


async def resolve_whatsapp_instance(
    context: ExecutionContext, connector_instance_id_str: str
) -> ConnectorInstance | Failure:
    try:
        connector_instance_id = uuid.UUID(connector_instance_id_str)
    except ValueError:
        return Failure(f"connector_instance_id {connector_instance_id_str!r} is not a valid UUID")

    instance = await connector_service.get_instance(
        context.session, tenant_id=context.tenant_id, instance_id=connector_instance_id
    )
    if instance is None:
        return Failure(f"connector instance {connector_instance_id} not found for this tenant")
    return instance
