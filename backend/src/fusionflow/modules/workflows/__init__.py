"""Workflow engine module (plan M5): builder-authored graphs, publish-time
validation, event-driven execution.

Importing this package registers every built-in node/trigger type (see
`nodes/__init__.py`) as a side effect, the same pattern
`fusionflow.db.models` uses for ORM class registration. Anything that needs
the node/trigger registries populated (the router, the outbox poller, a
test) should import this package - or `fusionflow.modules.workflows.nodes`
directly - before using `engine.registry.node_executor_registry` /
`trigger_registry`.
"""

from fusionflow.modules.workflows import nodes as _nodes  # noqa: F401
