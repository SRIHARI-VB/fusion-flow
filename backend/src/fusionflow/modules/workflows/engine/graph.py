"""Shared React-Flow graph schema + traversal helpers.

Used by both the execution engine (`run_loop.py`) and publish-time
validation (`validation.py`) so the two never disagree about what a node
or edge looks like. Field aliases match `@xyflow/react`'s JSON shape
(`sourceHandle`/`targetHandle`, camelCase `nodeType` inside `data`) so the
frontend can round-trip `workflow_versions.graph` without a translation
layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeData(BaseModel):
    """The payload React Flow stores under `node.data`.

    `node_type` is the registry key (e.g. `manual.test_trigger`,
    `log.noop`) — distinct from React Flow's own `node.type`, which only
    selects which custom node *component* renders the card (trigger/action/
    condition) and is not read by the engine at all.
    """

    model_config = ConfigDict(populate_by_name=True)

    node_type: str = Field(alias="nodeType")
    label: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str | None = None  # react-flow visual node type; engine ignores it
    data: GraphNodeData
    position: dict[str, float] = Field(default_factory=dict)
    # Maps 1:1 onto React Flow v12's own `parentId`/`extent: "parent"` node
    # nesting - the persisted graph JSON *is* the React Flow node shape, no
    # translation layer. Set only for a node embedded inside a container
    # (Loop/TryCatch/Parallel); `None` for every top-level node.
    parent_id: str | None = Field(default=None, alias="parentId")


class EdgeFilter(BaseModel):
    """A simple per-edge guard: this edge is only followed if
    `field_path`'s resolved value satisfies `operator`/`value` against the
    run's variable context — the same `field op value` shape and operator
    set `condition.field_compare`/`condition.multi_branch` already use
    (`engine.conditions.evaluate_condition`), applied to a connection
    instead of a dedicated condition node. Lets an author add a trivial
    per-connection guard without inserting an extra node for it (mirrors
    Make.com's connection filters)."""

    model_config = ConfigDict(populate_by_name=True)

    field_path: str
    operator: str = "eq"
    value: Any = None


class GraphEdgeData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filter: EdgeFilter | None = None
    #: Pure canvas annotation - no execution effect. React Flow already
    #: supports labeled edges natively.
    label: str | None = None


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: str
    target: str
    source_handle: str | None = Field(default=None, alias="sourceHandle")
    target_handle: str | None = Field(default=None, alias="targetHandle")
    data: GraphEdgeData | None = None


class WorkflowGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def node_by_id(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def trigger_nodes(self) -> list[GraphNode]:
        # Local import: avoids a module-load cycle (registry.py does not
        # import graph.py, but importing it eagerly at module scope here
        # would run before nodes/* has necessarily registered anything).
        from fusionflow.modules.workflows.engine.registry import trigger_registry

        trigger_types = {t.trigger_type for t in trigger_registry.all()}
        return [n for n in self.nodes if n.data.node_type in trigger_types]

    def outgoing_edges(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source == node_id]

    def adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj.setdefault(e.source, []).append(e.target)
        return adj

    def children_of(self, node_id: str) -> list[GraphNode]:
        """Nodes embedded directly inside the container `node_id` (their
        `parentId == node_id`) — not recursive, since a grandchild's own
        `parentId` points at its immediate parent container, not this one."""
        return [n for n in self.nodes if n.parent_id == node_id]

    def is_container(self, node_id: str) -> bool:
        """Whether `node_id`'s registered executor opts into embedding
        (`can_contain_children = True`) — Loop/TryCatch/Parallel today."""
        # Local import: same module-load-cycle reason as `trigger_nodes`.
        from fusionflow.modules.workflows.engine.registry import node_executor_registry

        node = self.node_by_id(node_id)
        if node is None:
            return False
        executor = node_executor_registry.get(node.data.node_type)
        return executor is not None and executor.can_contain_children

    def child_roots(self, container_id: str) -> list[GraphNode]:
        """The children of `container_id` that have no incoming edge from
        another child of the same container — i.e. where a mini traversal
        of the container's body should start. For Loop/TryCatch this is
        normally exactly one node (the head of a linear body chain); for
        Parallel, each root is the start of one concurrent branch."""
        children = self.children_of(container_id)
        child_ids = {c.id for c in children}
        targets_within = {e.target for e in self.edges if e.source in child_ids and e.target in child_ids}
        return [c for c in children if c.id not in targets_within]

    @classmethod
    def from_json(cls, raw: dict[str, Any] | None) -> "WorkflowGraph":
        if not raw:
            return cls()
        return cls.model_validate(raw)
