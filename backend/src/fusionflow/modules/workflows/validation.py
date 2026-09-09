"""Publish-time static validation — the plan's 5 required checks, run from
`service.publish_workflow` on every `POST /workflows/{id}/publish`.

`validate_for_publish` collects every failure across all 5 rules rather
than stopping at the first, so the builder UI's validation panel can show
every failing check in one pass. Never mutates the DB itself — the caller
persists `validation_status`/`validation_errors` onto the version.

Severity: most failures are hard errors (publish is blocked, `valid=False`
is returned) except one — the connector *state* check inside rule 2 is a
soft warning, downgraded deliberately (see `_check_connector_references`)
because it needs the connector-framework module, which does not exist in
every build this engine is tested against.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import node_executor_registry

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    severity: Severity
    message: str
    node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "node_id": self.node_id,
        }


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def status(self) -> str:
        return "invalid" if self.has_errors else "valid"

    def to_json(self) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self.issues]


async def validate_for_publish(
    session: AsyncSession, *, tenant_id: uuid.UUID, graph: WorkflowGraph
) -> ValidationResult:
    result = ValidationResult()
    _check_missing_required_fields(graph, result)
    await _check_connector_references(session, tenant_id, graph, result)
    _check_unreachable_nodes(graph, result)
    _check_invalid_branches(graph, result)
    _check_unsafe_loops(graph, result)
    return result


# --- Rule 1: missing required fields --------------------------------------


def _check_missing_required_fields(graph: WorkflowGraph, result: ValidationResult) -> None:
    for node in graph.nodes:
        executor = node_executor_registry.get(node.data.node_type)
        if executor is None:
            result.issues.append(
                ValidationIssue(
                    rule="missing_required_fields",
                    severity="error",
                    node_id=node.id,
                    message=f"unknown node type {node.data.node_type!r}",
                )
            )
            continue
        try:
            executor.validate_config(node.data.config)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else None
            detail = first["msg"] if first else str(exc)
            result.issues.append(
                ValidationIssue(
                    rule="missing_required_fields",
                    severity="error",
                    node_id=node.id,
                    message=f"invalid config for {node.data.node_type}: {detail}",
                )
            )


# --- Rule 2: disconnected connector references ----------------------------


async def _check_connector_references(
    session: AsyncSession, tenant_id: uuid.UUID, graph: WorkflowGraph, result: ValidationResult
) -> None:
    try:
        from fusionflow.modules.connectors.models import ConnectorInstance  # type: ignore[import-not-found]
    except ImportError:
        ConnectorInstance = None  # noqa: N806 - connectors module may not exist in this build

    for node in graph.nodes:
        raw_id = node.data.config.get("connector_instance_id")
        if not raw_id:
            continue

        try:
            connector_uuid = uuid.UUID(str(raw_id))
        except ValueError:
            result.issues.append(
                ValidationIssue(
                    rule="disconnected_connector_reference",
                    severity="error",
                    node_id=node.id,
                    message=f"connector_instance_id {raw_id!r} is not a valid UUID",
                )
            )
            continue

        if ConnectorInstance is None:
            # Best-effort only: can't verify tenant ownership without the
            # connectors module. Soft warning, not a hard block.
            result.issues.append(
                ValidationIssue(
                    rule="disconnected_connector_reference",
                    severity="warning",
                    node_id=node.id,
                    message=(
                        "connector framework not available in this build — "
                        "connector reference could not be verified"
                    ),
                )
            )
            continue

        instance = await session.get(ConnectorInstance, connector_uuid)
        if instance is None or instance.tenant_id != tenant_id:
            result.issues.append(
                ValidationIssue(
                    rule="disconnected_connector_reference",
                    severity="error",
                    node_id=node.id,
                    message=f"connector instance {raw_id} does not exist for this tenant",
                )
            )
            continue

        # Soft warning only (plan: "state check can be a soft warning") -
        # field name is defensive (`state` today; `status` as a fallback)
        # since this module is built in parallel with the connector
        # framework and the exact attribute could still move.
        state = getattr(instance, "state", None) or getattr(instance, "status", None)
        if state is not None and str(getattr(state, "value", state)) not in {"connected", "action_required"}:
            result.issues.append(
                ValidationIssue(
                    rule="disconnected_connector_reference",
                    severity="warning",
                    node_id=node.id,
                    message=f"connector instance {raw_id} is not connected (state={state})",
                )
            )


# --- Rule 3: unreachable nodes ---------------------------------------------


def _check_unreachable_nodes(graph: WorkflowGraph, result: ValidationResult) -> None:
    trigger_ids = [n.id for n in graph.trigger_nodes()]
    if not trigger_ids:
        result.issues.append(
            ValidationIssue(
                rule="unreachable_nodes",
                severity="error",
                node_id=None,
                message="workflow has no trigger node",
            )
        )
        return

    adjacency = graph.adjacency()
    reachable: set[str] = set()
    frontier = list(trigger_ids)
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(adjacency.get(current, []))

    for node in graph.nodes:
        if node.id not in reachable:
            result.issues.append(
                ValidationIssue(
                    rule="unreachable_nodes",
                    severity="error",
                    node_id=node.id,
                    message=f"node {node.id} is not reachable from any trigger node",
                )
            )


# --- Rule 4: invalid branches ------------------------------------------------


def _check_invalid_branches(graph: WorkflowGraph, result: ValidationResult) -> None:
    for node in graph.nodes:
        executor = node_executor_registry.get(node.data.node_type)
        if executor is None or not executor.output_handles:
            continue

        outgoing = graph.outgoing_edges(node.id)
        wired_counts: dict[str, int] = {}
        for edge in outgoing:
            handle = edge.source_handle or "default"
            wired_counts[handle] = wired_counts.get(handle, 0) + 1
            if handle not in executor.output_handles:
                result.issues.append(
                    ValidationIssue(
                        rule="invalid_branches",
                        severity="error",
                        node_id=node.id,
                        message=f"edge {edge.id} references undeclared output handle {handle!r}",
                    )
                )

        for handle in executor.output_handles:
            count = wired_counts.get(handle, 0)
            if count == 0:
                result.issues.append(
                    ValidationIssue(
                        rule="invalid_branches",
                        severity="error",
                        node_id=node.id,
                        message=f"output handle {handle!r} is not wired to any edge",
                    )
                )
            elif count > 1:
                result.issues.append(
                    ValidationIssue(
                        rule="invalid_branches",
                        severity="error",
                        node_id=node.id,
                        message=(
                            f"output handle {handle!r} is wired to {count} edges, expected exactly one"
                        ),
                    )
                )


# --- Rule 5: unsafe loops ----------------------------------------------------


def _check_unsafe_loops(graph: WorkflowGraph, result: ValidationResult) -> None:
    adjacency = graph.adjacency()
    for cycle in _find_cycles(adjacency):
        if _cycle_is_loop_safe(graph, cycle):
            continue
        result.issues.append(
            ValidationIssue(
                rule="unsafe_loops",
                severity="error",
                node_id=cycle[0],
                message=(
                    f"unsafe cycle detected: {' -> '.join(cycle)} — add a loop-safe "
                    "(max-iteration) node to the cycle to allow publish"
                ),
            )
        )


def _cycle_is_loop_safe(graph: WorkflowGraph, cycle: list[str]) -> bool:
    for node_id in cycle:
        node = graph.node_by_id(node_id)
        if node is None:
            continue
        executor = node_executor_registry.get(node.data.node_type)
        if executor is None or not executor.loop_safety_field:
            continue
        if node.data.config.get(executor.loop_safety_field):
            return True
    return False


def _find_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """DFS-based cycle detection. Returns one representative node list per
    back-edge found — not exhaustive of every simple cycle in a densely
    connected graph, but sufficient for "does an unsafe cycle exist"."""
    color: dict[str, int] = {}  # 0=unvisited (default), 1=in-stack, 2=done
    cycles: list[list[str]] = []
    stack: list[str] = []

    def dfs(node_id: str) -> None:
        color[node_id] = 1
        stack.append(node_id)
        for neighbor in adjacency.get(node_id, []):
            if color.get(neighbor, 0) == 0:
                dfs(neighbor)
            elif color.get(neighbor) == 1:
                cycle_start = stack.index(neighbor)
                cycles.append(stack[cycle_start:] + [neighbor])
        stack.pop()
        color[node_id] = 2

    for node_id in list(adjacency):
        if color.get(node_id, 0) == 0:
            dfs(node_id)
    return cycles
