"""`module.create` — generic node type: create a row in any fixed module
that supports it through its registered `ModuleQueryAdapter`.

Routes through the same `admin_service.get_resource_limit` +
per-module count check the REST create routes already use
(`connectors/deps.py::enforce_resource_limit`), called directly here
(there is no FastAPI request/response cycle inside a node executor to hang
a `Depends` off) - so a workflow cannot bypass a tenant's plan-based
resource limits. Payments has no create adapter method at all (raises
`NotImplementedError`, surfaced as a clean `Failure`) - see the Phase 6
plan for why.
"""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.catalog.models import ProductServiceType
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.kb import service as kb_service
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.nodes import _module_adapters  # noqa: F401 - side-effect import


async def _count_products(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return await catalog_service.count_products_services(session, tenant_id, entity_type=ProductServiceType.PRODUCT)


async def _count_services(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return await catalog_service.count_products_services(session, tenant_id, entity_type=ProductServiceType.SERVICE)


#: Only modules with a resource-limit concept (see `admin/service.py`'s
#: `RESOURCE_LIMIT_KEYS`) appear here - orders/payments/tickets have none.
_COUNT_FNS: dict[str, Callable[[AsyncSession, uuid.UUID], Awaitable[int]]] = {
    "products": _count_products,
    "services": _count_services,
    "coupons": catalog_service.count_coupons,
    "offers": catalog_service.count_offers,
    "customers": customers_service.count_customers,
    "kb": kb_service.count_articles,
}


_OUTPUT_SCHEMA = {"type": "object", "properties": {"item": {"type": "object"}}}


class ModuleCreateConfig(BaseModel):
    module: str = Field(min_length=1, description="Catalog module key, e.g. 'products', 'customers'.")
    fields: dict[str, Any] = Field(default_factory=dict)


class ModuleCreateExecutor(NodeExecutor):
    node_type = "module.create"
    kind = "action"
    category = "Data"
    label = "Create Module Record"
    description = "Creates a new row in a fixed module (not every module supports this - see Payments/Orders)."
    config_model = ModuleCreateConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ModuleCreateConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        count_fn = _COUNT_FNS.get(config.module)
        if count_fn is not None:
            limit = await admin_service.get_resource_limit(
                context.session, tenant_id=context.tenant_id, resource_key=config.module
            )
            if limit is not None:
                current = await count_fn(context.session, context.tenant_id)
                if current >= limit:
                    return Failure(f"tenant has reached its plan's limit of {limit} for {config.module!r}")

        fields = interpolate_dict_values(config.fields, context.variables)
        from fusionflow.modules.business_objects.workflow_adapter import CustomObjectQueryAdapter
        if isinstance(adapter, CustomObjectQueryAdapter):
            adapter.created_by_run_id = context.run_id
        try:
            item = await adapter.create(context.session, tenant_id=context.tenant_id, fields=fields)
        except NotImplementedError as exc:
            return Failure(str(exc))
        except ValidationError as exc:
            return Failure(f"invalid fields for {config.module!r}: {exc}")
        except ValueError as exc:
            # A custom-object type's record-payload validation (or any
            # other adapter-level domain check, mirroring
            # `orders/workflow_adapter.py`'s "only status field" rejection
            # for `module.update`) signals via `ValueError` - translated
            # here to a clean `Failure` instead of an uncaught exception.
            return Failure(str(exc))

        return Success(output={"item": item})


node_executor_registry.register(ModuleCreateExecutor())
