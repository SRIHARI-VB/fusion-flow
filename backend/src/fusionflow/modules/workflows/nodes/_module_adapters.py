"""Import-for-side-effect: registers every `ModuleQueryAdapter` into
`modules/workflows/engine/module_registry.py`'s process-wide singleton.

Imported once by `module_list.py` (the first of the four generic
module-CRUD node types to need the registry populated) - matches
`connectors/router.py`'s `# noqa: F401` side-effect-import convention for
provider adapters.
"""

from __future__ import annotations

from fusionflow.modules.catalog import workflow_adapter as _catalog_workflow_adapter  # noqa: F401
from fusionflow.modules.customers import workflow_adapter as _customers_workflow_adapter  # noqa: F401
from fusionflow.modules.kb import workflow_adapter as _kb_workflow_adapter  # noqa: F401
from fusionflow.modules.orders import workflow_adapter as _orders_workflow_adapter  # noqa: F401
from fusionflow.modules.payments import workflow_adapter as _payments_workflow_adapter  # noqa: F401
from fusionflow.modules.tickets import workflow_adapter as _tickets_workflow_adapter  # noqa: F401
