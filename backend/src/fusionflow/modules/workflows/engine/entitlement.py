"""Runtime entitlement checks for the workflow engine.

Admin revokes (`ConnectorAccessOverride`) and role restrictions used to be
enforced only at HTTP routers. This module lets the engine (run loop,
pollers) and webhooks re-verify, at execution time, that the tenant still
has tenant-level ('granted', role=None) access to every module/connector a
graph touches.

A per-call `cache` dict (key -> status) avoids N queries per run; callers
that want a short-lived cache just pass the same dict around.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.graph import GraphNode, WorkflowGraph

logger = logging.getLogger(__name__)

EntitlementCache = dict[str, tuple[str, str]]  # key -> (status, display_name)


def node_required_keys(node: GraphNode) -> set[str]:
    """Catalog keys (modules / connector types) this one node touches."""
    from fusionflow.modules.workflows.engine.registry import node_executor_registry, trigger_registry

    node_type = node.data.node_type
    config = node.data.config or {}
    keys: set[str] = set()

    executor = node_executor_registry.get(node_type)
    if executor is not None and executor.required_connector_type_key:
        keys.add(executor.required_connector_type_key)
    trigger = trigger_registry.get(node_type)
    if trigger is not None and trigger.required_connector_type_key:
        keys.add(trigger.required_connector_type_key)

    module = config.get("module")
    if isinstance(module, str) and module and (node_type.startswith("module.") or node_type.startswith("record.")):
        keys.add(module)

    source = config.get("source")
    if isinstance(source, dict) and source.get("kind") == "module" and isinstance(source.get("module"), str):
        keys.add(source["module"])
    return keys


def graph_required_keys(graph: WorkflowGraph) -> set[str]:
    keys: set[str] = set()
    for node in graph.nodes:
        keys |= node_required_keys(node)
    return keys


def graph_required_keys_from_json(raw: dict[str, Any] | None) -> set[str]:
    try:
        return graph_required_keys(WorkflowGraph.from_json(raw))
    except Exception:  # noqa: BLE001 - a malformed stored graph must not break a list endpoint
        return set()


async def key_access(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    key: str,
    cache: EntitlementCache | None = None,
) -> tuple[str, str]:
    """(status, display_name) for one catalog key at tenant level. Keys that
    are not in the connector-type catalog (e.g. a tenant's own custom business
    object) are not entitlement-gated and resolve to 'granted'."""
    if cache is not None and key in cache:
        return cache[key]

    from fusionflow.modules.connectors import service as connector_service

    connector_type = await connector_service.get_connector_type_by_key(session, key)
    if connector_type is None:
        result = ("granted", key)
    else:
        status = await connector_service.resolve_module_access(
            session, tenant_id=tenant_id, connector_type=connector_type, role=None
        )
        result = (status, connector_type.display_name)
    if cache is not None:
        cache[key] = result
    return result


async def find_blocked(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    keys: Iterable[str],
    cache: EntitlementCache | None = None,
) -> list[tuple[str, str, str]]:
    """[(key, display_name, status)] for each key that is NOT granted."""
    blocked: list[tuple[str, str, str]] = []
    for key in sorted(set(keys)):
        status, display_name = await key_access(session, tenant_id=tenant_id, key=key, cache=cache)
        if status != "granted":
            blocked.append((key, display_name, status))
    return blocked


def revoked_message(key: str, display_name: str | None = None) -> str:
    return f"Module '{key}' was revoked for this business by an administrator"


async def first_block_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    keys: Iterable[str],
    cache: EntitlementCache | None = None,
) -> str | None:
    blocked = await find_blocked(session, tenant_id=tenant_id, keys=keys, cache=cache)
    if not blocked:
        return None
    key, _name, _status = blocked[0]
    return revoked_message(key)


async def tenant_has_access(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    keys: Iterable[str],
    cache: EntitlementCache | None = None,
) -> bool:
    return not await find_blocked(session, tenant_id=tenant_id, keys=keys, cache=cache)
