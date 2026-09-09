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


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    source: str
    target: str
    source_handle: str | None = Field(default=None, alias="sourceHandle")
    target_handle: str | None = Field(default=None, alias="targetHandle")


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

    @classmethod
    def from_json(cls, raw: dict[str, Any] | None) -> "WorkflowGraph":
        if not raw:
            return cls()
        return cls.model_validate(raw)
