"""Built-in node types.

The first three (`manual_test_trigger`, `log_noop`, `condition_field_compare`)
are fully generic/self-contained — a small set that doesn't depend on any
other module, so the engine is fully testable in isolation. The next four
(`whatsapp_message_received`, `order_created`, `send_whatsapp_message`,
`create_ticket`) are the connector/fixed-connector-backed node types that
make the plan's M5 sample scenario ("new WhatsApp message → keyword branch
→ create ticket or auto-reply") buildable — they depend on
`modules/connectors/whatsapp` and `modules/tickets` respectively. The next
three (`flow_loop`, `flow_try_catch`, `flow_parallel`) are the container
node types (`can_contain_children = True`) added for the advanced-workflow-
engine phase — genuinely new execution semantics, so unlike most later
node/integration additions (see `run_loop.py`'s and the generic-executor
nodes' docstrings for the "catalog/config, not code" extensibility
principle) these three are real new Python classes, deliberately. The
last four (`connector_action`, `http_request`, `condition_multi_branch`,
`data_transform`) are the generic, highly-parameterized executors that
*are* the extensibility principle in practice — a new connector
capability, a new simple third-party API, a new comparison case, or a new
derived value should reach for one of these (plus, for connector/HTTP
templates, an admin-managed `WorkflowNodeTemplate` catalog row - see
`modules/admin/models.py`) rather than a new node type.

Importing this package registers all fourteen with the process-wide
`node_executor_registry` / `trigger_registry` singletons in
`engine/registry.py` as a side effect — matching `fusionflow.db.models`'s
"import for side effect" pattern for ORM classes.
"""

from fusionflow.modules.workflows.nodes import (  # noqa: F401
    condition_field_compare,
    condition_multi_branch,
    connector_action,
    create_ticket,
    data_transform,
    flow_loop,
    flow_parallel,
    flow_try_catch,
    http_request,
    log_noop,
    manual_test_trigger,
    order_created,
    send_whatsapp_message,
    whatsapp_message_received,
)

__all__ = [
    "condition_field_compare",
    "condition_multi_branch",
    "connector_action",
    "create_ticket",
    "data_transform",
    "flow_loop",
    "flow_parallel",
    "flow_try_catch",
    "http_request",
    "log_noop",
    "manual_test_trigger",
    "order_created",
    "send_whatsapp_message",
    "whatsapp_message_received",
]
