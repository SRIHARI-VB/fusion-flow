"""Built-in node types.

The first three (`manual_test_trigger`, `log_noop`, `condition_field_compare`)
are fully generic/self-contained — a small set that doesn't depend on any
other module, so the engine is fully testable in isolation. The next four
(`whatsapp_message_received`, `order_created`, `send_whatsapp_message`,
`create_ticket`) are the connector/fixed-connector-backed node types that
make the plan's M5 sample scenario ("new WhatsApp message → keyword branch
→ create ticket or auto-reply") buildable — they depend on
`modules/connectors/whatsapp` and `modules/tickets` respectively.

Importing this package registers all seven with the process-wide
`node_executor_registry` / `trigger_registry` singletons in
`engine/registry.py` as a side effect — matching `fusionflow.db.models`'s
"import for side effect" pattern for ORM classes.
"""

from fusionflow.modules.workflows.nodes import (  # noqa: F401
    condition_field_compare,
    create_ticket,
    log_noop,
    manual_test_trigger,
    order_created,
    send_whatsapp_message,
    whatsapp_message_received,
)

__all__ = [
    "condition_field_compare",
    "create_ticket",
    "log_noop",
    "manual_test_trigger",
    "order_created",
    "send_whatsapp_message",
    "whatsapp_message_received",
]
