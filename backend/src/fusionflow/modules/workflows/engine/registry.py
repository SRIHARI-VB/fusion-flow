"""Node/trigger type registries — the workflow engine's plugin surface.

Two registries, matching the plan's "Workflow Engine" section literally:

* `TriggerRegistry`      — `trigger_type -> config schema/metadata`. Read by
  the palette endpoint and by the outbox poller when it needs to describe
  what a trigger *is* (it does not execute anything itself).
* `NodeExecutorRegistry` — `node_type -> NodeExecutor`. Read by the run
  loop to actually execute a graph node, and also by the palette endpoint
  for action/condition metadata.

A built-in trigger node type (e.g. `manual.test_trigger`) is registered in
*both*: once as a `TriggerDefinition` (so it's listed under the Triggers
palette category and can back a `WorkflowTrigger` row) and once as a
`NodeExecutor` (so the run loop can execute it like any other graph node —
the trigger node's "execution" is simply seeding the run's variable
context with the payload that caused it to fire).

Any module — built-in (`modules/workflows/nodes/*`) or a future connector
(WhatsApp, Razorpay, ...) — registers into the two singletons at the
bottom of this file at import time, the same "import for side effect"
pattern `fusionflow.db.models` uses for ORM classes.
"""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a circular import
    from fusionflow.modules.workflows.engine.graph import WorkflowGraph

NodeKind = Literal["trigger", "action", "condition"]


@dataclass(frozen=True)
class NodeTypeMeta:
    """Palette + validation metadata for one node type. JSON-serializable
    (via `dataclasses.asdict`-style access from the router) for
    `GET /workflows/node-types`."""

    node_type: str
    kind: NodeKind
    category: str
    label: str
    description: str
    config_schema: dict[str, Any]
    output_handles: list[str] | None = None
    optional_output_handles: list[str] | None = None
    loop_safety_field: str | None = None
    can_contain_children: bool = False
    child_role: str | None = None


#: Signature of `ExecutionContext.run_children` - see its docstring below.
#: Kept as a module-level alias (not inlined) so container node modules can
#: import and type-hint against it without repeating the shape.
RunChildrenFn = Callable[[list[str], dict[str, Any], set[str]], Awaitable[None]]


@dataclass(frozen=True)
class ExecutionContext:
    """Everything a `NodeExecutor.execute` needs for one step.

    `session` is already tenant-scoped (`SET LOCAL` applied) by whoever
    started the run (the route handler for simulate, the outbox poller job
    for inbox-driven runs) — node executors must never open their own
    session or bypass this one.
    """

    session: AsyncSession
    tenant_id: uuid.UUID
    run_id: uuid.UUID
    node_id: str
    config: dict[str, Any]
    variables: dict[str, Any]
    # The two fields below are only populated for a node whose executor
    # has `can_contain_children = True` (run_loop.py sets them; every
    # other node type gets `None`, and never needs them). Not folded into
    # every node's contract because embedding is opt-in, same as
    # `output_handles`/`loop_safety_field` - see NodeExecutor's docstring.
    graph: "WorkflowGraph | None" = None
    # Runs the child sub-graph rooted at the given node ids, restricted to
    # `allowed_node_ids`, against a *caller-owned* scoped `variables` dict
    # (mutated in place - each executed child's output lands under
    # `variables[child.id]`, exactly like the top-level run loop does for
    # top-level nodes, but scoped to this copy so it never leaks into the
    # container's own outer variables). Raises `ChildExecutionError` (see
    # run_loop.py) if any child fails or exhausts its retries - the
    # container decides whether to catch that (Try/Catch) or let it
    # propagate (Loop, Parallel, and Try/Catch itself when no "error"
    # handle is wired).
    run_children: RunChildrenFn | None = None


@dataclass(frozen=True)
class Success:
    """The node ran; `output` becomes `workflow_run_steps.output` and is
    merged into the run's variable context under the node's id."""

    output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Failure:
    """The node failed; the run loop force-fails the whole run."""

    error: str


@dataclass(frozen=True)
class Branch:
    """Condition-node result: which declared output handle(s) fired.

    The run loop only follows edges whose `sourceHandle` is in
    `selected_edge_handles` — every other outgoing edge is left untaken,
    matching the plan's "only the matched edge for condition nodes" rule.
    """

    selected_edge_handles: list[str]
    output: dict[str, Any] = field(default_factory=dict)


NodeResult = Success | Failure | Branch


class NodeExecutor(abc.ABC):
    """Base class for every node type the run loop can execute.

    Subclasses set the class attributes below and implement `execute`.
    `config_model`, when set, is both the source of the JSON config schema
    exposed to the builder UI and the validator
    `validation.py`'s "missing required fields" rule runs each node's
    `data.config` through.
    """

    node_type: str
    kind: NodeKind = "action"
    category: str = "Generic"
    label: str = ""
    description: str = ""
    config_model: type[BaseModel] | None = None
    # Condition nodes only: the full set of output handle ids they can
    # branch to (e.g. ["true", "false"]). None/empty means "not a branching
    # node" — the run loop follows every outgoing edge for such nodes.
    # validation.py's rule 4 requires each of these to be wired exactly
    # once.
    output_handles: list[str] | None = None
    # Named handles that MAY be wired at most once each, but don't have to
    # be wired at all - distinct from `output_handles` (required, exactly
    # once). Try/Catch is the only user today: an author can leave "error"
    # unwired (falls back to today's fail-fast propagation) and/or leave
    # "success" unwired (falls back to a plain Success instead of a
    # Branch) - see nodes/flow_try_catch.py.
    optional_output_handles: list[str] | None = None
    # Config key whose presence (truthy value) marks this node type
    # loop-safe when used inside a cycle (validation.py rule 5). None means
    # this node type can never make a cycle safe.
    loop_safety_field: str | None = None
    # Opt-in retry-with-backoff (run_loop.py): default off, so every
    # existing node type keeps today's fail-fast-on-exception behavior
    # unless it explicitly opts in. Meant for nodes that make real outbound
    # calls (a flaky third-party API, a transient DB hiccup) - not for pure
    # in-process nodes, where a retry can never change the outcome.
    retryable: bool = False
    max_retries: int = 0
    # Opt-in embedding (run_loop.py / graph.py): only Loop/TryCatch/Parallel
    # set `can_contain_children = True`. `child_role` is a free-text label
    # ("loop_body" | "try_body" | "parallel_branch") the frontend/validation
    # can use to describe what a child of this container represents; the
    # engine itself does not branch on its value.
    can_contain_children: bool = False
    child_role: str | None = None

    @classmethod
    def meta(cls) -> NodeTypeMeta:
        schema = cls.config_model.model_json_schema() if cls.config_model else {}
        return NodeTypeMeta(
            node_type=cls.node_type,
            kind=cls.kind,
            category=cls.category,
            label=cls.label or cls.node_type,
            description=cls.description,
            config_schema=schema,
            output_handles=cls.output_handles,
            optional_output_handles=cls.optional_output_handles,
            loop_safety_field=cls.loop_safety_field,
            can_contain_children=cls.can_contain_children,
            child_role=cls.child_role,
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        """Raise `pydantic.ValidationError` if `config` doesn't fit this
        node type's schema. No-op when the node type declares no schema."""
        if self.config_model is not None:
            self.config_model.model_validate(config)

    @abc.abstractmethod
    async def execute(self, context: ExecutionContext) -> NodeResult: ...


class NodeExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, NodeExecutor] = {}

    def register(self, executor: NodeExecutor) -> None:
        if executor.node_type in self._executors:
            raise ValueError(f"node type already registered: {executor.node_type!r}")
        self._executors[executor.node_type] = executor

    def get(self, node_type: str) -> NodeExecutor | None:
        return self._executors.get(node_type)

    def all(self) -> list[NodeExecutor]:
        return list(self._executors.values())


@dataclass(frozen=True)
class TriggerDefinition:
    """Metadata for one trigger type — no execution logic here. The
    matching graph node still needs a `NodeExecutor` registered under the
    same `trigger_type`/`node_type` for the run loop to execute it."""

    trigger_type: str
    category: str
    label: str
    description: str
    config_model: type[BaseModel] | None = None

    def meta(self) -> NodeTypeMeta:
        schema = self.config_model.model_json_schema() if self.config_model else {}
        return NodeTypeMeta(
            node_type=self.trigger_type,
            kind="trigger",
            category=self.category,
            label=self.label,
            description=self.description,
            config_schema=schema,
        )


class TriggerRegistry:
    def __init__(self) -> None:
        self._triggers: dict[str, TriggerDefinition] = {}

    def register(self, definition: TriggerDefinition) -> None:
        if definition.trigger_type in self._triggers:
            raise ValueError(f"trigger type already registered: {definition.trigger_type!r}")
        self._triggers[definition.trigger_type] = definition

    def get(self, trigger_type: str) -> TriggerDefinition | None:
        return self._triggers.get(trigger_type)

    def all(self) -> list[TriggerDefinition]:
        return list(self._triggers.values())


# Process-wide singletons. Built-in nodes (modules/workflows/nodes/*)
# register into these at import time; future connector-contributed node
# types (e.g. `whatsapp.message_received`, `send_whatsapp_message`) import
# the same two singletons from this module and do the same.
node_executor_registry = NodeExecutorRegistry()
trigger_registry = TriggerRegistry()
