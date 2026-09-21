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
    subcategory: str | None
    label: str
    description: str
    config_schema: dict[str, Any]
    output_handles: list[str] | None = None
    optional_output_handles: list[str] | None = None
    loop_safety_field: str | None = None
    can_contain_children: bool = False
    child_role: str | None = None
    # Entitlement gate (Phase 7 Part A): the `connector_types.key` a tenant
    # must have "granted" access to for this node type to appear in the
    # palette. None means "no requirement" - every pre-Phase-7 node type.
    required_connector_type_key: str | None = None
    # Declared shape of this node type's `Success.output` (Phase 7 Part B),
    # same JSON-Schema-lite shape `config_schema` already uses. None means
    # "not statically knowable" (e.g. manual.test_trigger's author-defined
    # payload) or simply not yet catalogued.
    output_schema: dict[str, Any] | None = None
    # Composable-builder redesign: a `lucide-react` icon key for the
    # palette card (None falls back to the frontend's existing 3-icon
    # kind badge — Zap/PlayCircle/GitBranch — unchanged for every
    # pre-redesign node type). And the task-oriented palette bucket this
    # node shows under by default ("Talk to Customer" / "Records" /
    # "Payments" / "Flow Control" / "Advanced" / "Triggers") — additive,
    # layered above `category`/`subcategory` (still used by
    # `ChannelFilterBar`), not a replacement for them. `service.py`'s
    # `_default_palette_group` fills this in for any node type that
    # doesn't set one explicitly, so every entry always has a bucket.
    icon: str | None = None
    palette_group: str | None = None
    # "Workflow purpose" tag (recurring/bulk-messaging support): the set of
    # `Workflow.purpose` values this *trigger* type is allowed to appear
    # under in the palette - e.g. `["automation"]` for an event-driven
    # trigger, `["broadcast"]` for `broadcast.scheduled_send`. `None` means
    # "applicable regardless of purpose" (every non-trigger node type, plus
    # `manual.test_trigger`) - `service.list_node_types_with_templates`'s
    # purpose filter only ever excludes an entry that sets this AND doesn't
    # include the requested purpose.
    applicable_purposes: list[str] | None = None


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


@dataclass(frozen=True)
class Suspend:
    """A `can_suspend` node's result: the node has done its (one-shot) job
    for this pass — typically sending an outbound message — and the run
    should now pause until a matching reply arrives. `correlation_key`
    (e.g. a customer's phone number) is what a later inbound event must
    match, on the same connector instance, to resume this exact run (see
    `run_loop.RunSuspended`/`resume_run` and `engine.event_bus.
    find_pending_wait`)."""

    correlation_key: str


NodeResult = Success | Failure | Branch | Suspend


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
    # Optional second grouping level under `category` for the palette
    # (e.g. category="Messages", subcategory="Media"/"Location"/...) -
    # None means "no subgrouping," which is every pre-Phase-5 node type;
    # the frontend falls back to flat rendering for those, unchanged.
    subcategory: str | None = None
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
    # Opt-in pause/resume (Phase 8 Part A, run_loop.py): only a node type
    # whose `execute()` may return `Suspend` sets this. Gates validation
    # rule 7 (`validation.py::_check_no_suspend_in_container`) - a
    # suspending node cannot be embedded inside a container.
    can_suspend: bool = False
    # Entitlement gate (Phase 7 Part A) - see NodeTypeMeta's field docstring.
    required_connector_type_key: str | None = None
    # Declared output shape (Phase 7 Part B) - see NodeTypeMeta's field docstring.
    output_schema: dict[str, Any] | None = None
    # Composable-builder redesign - see NodeTypeMeta's field docstrings.
    icon: str | None = None
    palette_group: str | None = None
    # "Workflow purpose" tag - see NodeTypeMeta's field docstring. Only ever
    # meaningful for a `kind == "trigger"` node type; left `None` (the
    # default) on every action/condition/flow-control node type.
    applicable_purposes: list[str] | None = None

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        """Only overridden by a `can_suspend = True` executor: turn the
        inbound event payload that resumed the run (the same shape
        `WhatsAppAdapter._extract_inbound_message` produces) into the
        actual "answer" value this node asked for - e.g. free text, or
        whichever button/list row id the customer tapped. Mirrors
        `ConnectorAdapter.perform_action`'s "opt-in capability method"
        shape: the default raises since most node types never suspend."""
        raise NotImplementedError

    @classmethod
    def meta(cls) -> NodeTypeMeta:
        schema = cls.config_model.model_json_schema() if cls.config_model else {}
        return NodeTypeMeta(
            node_type=cls.node_type,
            kind=cls.kind,
            category=cls.category,
            subcategory=cls.subcategory,
            label=cls.label or cls.node_type,
            description=cls.description,
            config_schema=schema,
            output_handles=cls.output_handles,
            optional_output_handles=cls.optional_output_handles,
            loop_safety_field=cls.loop_safety_field,
            can_contain_children=cls.can_contain_children,
            child_role=cls.child_role,
            required_connector_type_key=cls.required_connector_type_key,
            output_schema=cls.output_schema,
            icon=cls.icon,
            palette_group=cls.palette_group,
            applicable_purposes=cls.applicable_purposes,
        )

    def validate_config(self, config: dict[str, Any]) -> None:
        """Raise `pydantic.ValidationError` if `config` doesn't fit this
        node type's schema. No-op when the node type declares no schema."""
        if self.config_model is not None:
            self.config_model.model_validate(config)

    def declared_output_handles(self, config: dict[str, Any]) -> list[str] | None:
        """Which output handles must be wired for *this specific node
        instance*, given its own `config`. Default just returns the
        static `output_handles` class attribute — overridden only by a
        node type whose handle set is config-dependent (today: just
        `condition.multi_branch`, where each configured "case" becomes
        its own handle — see that node's override, the only current user
        of this method). `validation.py`'s rule 4 calls this, not the raw
        attribute, so both the static and dynamic cases go through one
        code path."""
        return self.output_handles

    def declared_optional_output_handles(self, config: dict[str, Any]) -> list[str] | None:
        """Which output handles MAY be wired at most once each but don't
        have to be, for *this specific node instance* — mirrors
        `declared_output_handles`'s config-dependent pattern but for the
        optional side. Default just returns the static
        `optional_output_handles` class attribute (every pre-existing node
        type, e.g. `flow.try_catch`'s fixed `["success", "error"]`);
        overridden only by a node type whose optional handle set is
        config-dependent (today: `condition.multi_branch`, whose
        "no case matched" default handle name is itself configurable —
        see that node's override)."""
        return self.optional_output_handles

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
    subcategory: str | None = None
    required_connector_type_key: str | None = None
    output_schema: dict[str, Any] | None = None
    icon: str | None = None
    palette_group: str | None = None
    # "Workflow purpose" tag - see NodeTypeMeta's field docstring.
    applicable_purposes: list[str] | None = None

    def meta(self) -> NodeTypeMeta:
        schema = self.config_model.model_json_schema() if self.config_model else {}
        return NodeTypeMeta(
            node_type=self.trigger_type,
            kind="trigger",
            category=self.category,
            subcategory=self.subcategory,
            label=self.label,
            description=self.description,
            config_schema=schema,
            required_connector_type_key=self.required_connector_type_key,
            output_schema=self.output_schema,
            icon=self.icon,
            palette_group=self.palette_group or "Triggers",
            applicable_purposes=self.applicable_purposes,
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
