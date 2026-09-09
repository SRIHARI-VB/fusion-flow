"""Built-in, self-contained node types (see the workflows agent's task
scope: a small generic set that doesn't depend on any other module, so the
engine is fully testable in isolation before connector-specific node types
exist).

Importing this package registers all three with the process-wide
`node_executor_registry` / `trigger_registry` singletons in
`engine/registry.py` as a side effect — matching `fusionflow.db.models`'s
"import for side effect" pattern for ORM classes.
"""

from fusionflow.modules.workflows.nodes import (  # noqa: F401
    condition_field_compare,
    log_noop,
    manual_test_trigger,
)

__all__ = ["condition_field_compare", "log_noop", "manual_test_trigger"]
