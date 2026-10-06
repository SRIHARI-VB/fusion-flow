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
    _check_containment_validity(graph, result)
    _check_no_suspend_in_container(graph, result)
    await _check_module_entitlement(session, tenant_id, graph, result)
    return result


# --- Rule 8: module/connector entitlement ----------------------------------


async def _check_module_entitlement(
    session: AsyncSession, tenant_id: uuid.UUID, graph: WorkflowGraph, result: ValidationResult
) -> None:
    """Nodes that need a module/connector the tenant doesn't currently have
    (never granted, pending, denied or revoked by an administrator)."""
    from fusionflow.modules.workflows.engine import entitlement

    cache: dict = {}
    for node in graph.nodes:
        for key in sorted(entitlement.node_required_keys(node)):
            status, display_name = await entitlement.key_access(
                session, tenant_id=tenant_id, key=key, cache=cache
            )
            if status == "granted":
                continue
            result.issues.append(
                ValidationIssue(
                    rule="module_not_entitled",
                    severity="error",
                    node_id=node.id,
                    message=(
                        f"This workflow uses the {display_name} module, which is not available "
                        f"for this business (status: {status.replace('_', ' ')}). Remove the step "
                        "or ask an administrator for access."
                    ),
                )
            )


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

    # A container's own root children (`child_roots`) have no top-level
    # edge pointing at them by design - their reachability comes from
    # being embedded inside a reachable container, not from a graph edge
    # (see engine/graph.py's `children_of`/`child_roots`). Once a
    # container is reached via the normal edge-adjacency walk, its root
    # children are added to the frontier the same way an edge target
    # would be; from there, their own outgoing edges (which the plain
    # `adjacency()` map already includes, since intra-container edges are
    # ordinary graph edges) continue the walk as usual.
    adjacency = graph.adjacency()
    reachable: set[str] = set()
    frontier = list(trigger_ids)
    while frontier:
        current = frontier.pop()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(adjacency.get(current, []))
        if graph.is_container(current):
            frontier.extend(child.id for child in graph.child_roots(current))

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
        if executor is None:
            continue
        required = executor.declared_output_handles(node.data.config) or []
        optional = executor.declared_optional_output_handles(node.data.config) or []
        if not required and not optional:
            continue
        declared = set(required) | set(optional)

        outgoing = graph.outgoing_edges(node.id)
        wired_counts: dict[str, int] = {}
        for edge in outgoing:
            handle = edge.source_handle or "default"
            wired_counts[handle] = wired_counts.get(handle, 0) + 1
            if handle not in declared:
                result.issues.append(
                    ValidationIssue(
                        rule="invalid_branches",
                        severity="error",
                        node_id=node.id,
                        message=f"edge {edge.id} references undeclared output handle {handle!r}",
                    )
                )

        for handle in required:
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

        # Optional handles (Try/Catch's "success"/"error") may be left
        # completely unwired, but if wired at all, still at most once.
        for handle in optional:
            count = wired_counts.get(handle, 0)
            if count > 1:
                result.issues.append(
                    ValidationIssue(
                        rule="invalid_branches",
                        severity="error",
                        node_id=node.id,
                        message=(
                            f"optional output handle {handle!r} is wired to {count} edges, "
                            "expected at most one"
                        ),
                    )
                )


# --- Rule 5: unsafe loops ----------------------------------------------------


def _check_unsafe_loops(graph: WorkflowGraph, result: ValidationResult) -> None:
    adjacency = graph.adjacency()
    child_to_parent = {n.id: n.parent_id for n in graph.nodes if n.parent_id is not None}
    for cycle in _find_cycles(adjacency):
        if _cycle_is_loop_safe(graph, cycle):
            continue
        if _cycle_is_inside_a_loop_container(graph, cycle, child_to_parent):
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


def _cycle_is_inside_a_loop_container(
    graph: WorkflowGraph, cycle: list[str], child_to_parent: dict[str, str | None]
) -> bool:
    """A cycle entirely contained within one Loop container's own body is
    auto-safe: it's already bounded by that container's `max_iterations`
    local cap plus the run's global `loop_guard_count` ceiling, so it
    doesn't need a manually-set `loop_safety_field` node too. A cycle that
    spans multiple containers, or touches any top-level node, still needs
    one — this only recognizes a cycle 100% inside a single loop body."""
    parents = {child_to_parent.get(node_id) for node_id in cycle}
    if len(parents) != 1:
        return False
    (parent_id,) = parents
    if parent_id is None:
        return False
    parent_node = graph.node_by_id(parent_id)
    if parent_node is None:
        return False
    executor = node_executor_registry.get(parent_node.data.node_type)
    return executor is not None and executor.child_role == "loop_body"


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


# --- Rule 6: containment validity --------------------------------------------


def _check_containment_validity(graph: WorkflowGraph, result: ValidationResult) -> None:
    """Two checks, both closing off a malformed-graph bug class before a
    run ever starts: (1) a node's `parentId`, if set, must reference a
    node whose executor actually opts into embedding
    (`can_contain_children = True`) — a plain leaf node type can never be
    a parent; (2) an edge may not cross a container boundary — a child's
    edges must stay within the same immediate parent as the child itself
    (this also covers the container's own boundary-crossing edges being
    *allowed*, since the container itself has no `parentId` set unless
    it's nested, and a nested container's own edges are scoped by its own
    parent, exactly like any other child of that parent — see the parent
    lookup below)."""
    for node in graph.nodes:
        if node.parent_id is None:
            continue
        parent = graph.node_by_id(node.parent_id)
        if parent is None:
            result.issues.append(
                ValidationIssue(
                    rule="containment_validity",
                    severity="error",
                    node_id=node.id,
                    message=f"parent node {node.parent_id!r} does not exist",
                )
            )
            continue
        if not graph.is_container(node.parent_id):
            result.issues.append(
                ValidationIssue(
                    rule="containment_validity",
                    severity="error",
                    node_id=node.id,
                    message=(
                        f"parent node {node.parent_id!r} (type {parent.data.node_type!r}) "
                        "cannot contain child nodes"
                    ),
                )
            )

    child_to_parent = {n.id: n.parent_id for n in graph.nodes if n.parent_id is not None}
    for edge in graph.edges:
        source_parent = child_to_parent.get(edge.source)
        target_parent = child_to_parent.get(edge.target)
        if source_parent != target_parent:
            result.issues.append(
                ValidationIssue(
                    rule="containment_validity",
                    severity="error",
                    node_id=edge.source,
                    message=(
                        f"edge {edge.id} crosses a container boundary — a child node's edges must "
                        "stay within the same container as the child itself"
                    ),
                )
            )


# --- Rule 7: no pause/resume node inside a container (Phase 8 Part A) -------


def _check_no_suspend_in_container(graph: WorkflowGraph, result: ValidationResult) -> None:
    """A `can_suspend` node (e.g. `whatsapp.ask_question`) cannot be
    embedded inside a container (Loop/TryCatch/Parallel) - resuming
    mid-container would require modeling nested scoped state, an honest
    v1 scope cut (see Phase 8's plan section)."""
    for node in graph.nodes:
        if node.parent_id is None:
            continue
        executor = node_executor_registry.get(node.data.node_type)
        if executor is None or not executor.can_suspend:
            continue
        result.issues.append(
            ValidationIssue(
                rule="suspend_not_in_container",
                severity="error",
                node_id=node.id,
                message="a node that waits for a reply cannot be embedded inside a container (Loop/Try-Catch/Parallel)",
            )
        )
