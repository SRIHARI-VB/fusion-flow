"""`http.request` — the universal "integrate with any third-party REST
API" escape hatch every serious automation tool ships (n8n's HTTP
Request, Zapier's Webhooks, Make's HTTP module). Covers a genuinely new
external integration with **zero backend code changes, ever**, for
anything that doesn't need real OAuth/webhook lifecycle management (which
still correctly goes through a real `ConnectorAdapter` + `connector.
action` — this node is deliberately the lighter-weight option for
simpler cases, not a replacement for the adapter framework).

`url`/`headers` values/`body` (when a dict) support the same
`{{dot.path}}` templating as every other node in this module.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate, resolve_template_value

_DEFAULT_TIMEOUT_SECONDS = 15.0


class HttpRequestConfig(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=1, description="May reference the run context, e.g. 'https://api.example.com/{{trigger.id}}'.")
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | str | None = None
    timeout_seconds: float = Field(default=_DEFAULT_TIMEOUT_SECONDS, gt=0, le=60)


def _interpolate_body(body: dict[str, Any] | str | None, variables: dict[str, Any]) -> Any:
    if body is None:
        return None
    if isinstance(body, str):
        return resolve_template_value(body, variables)
    return {
        key: resolve_template_value(value, variables) if isinstance(value, str) else value
        for key, value in body.items()
    }


class HttpRequestExecutor(NodeExecutor):
    node_type = "http.request"
    kind = "action"
    category = "Integrations"
    label = "HTTP Request"
    description = "Calls any third-party HTTP API - the generic integration node for simple, non-OAuth APIs."
    config_model = HttpRequestConfig
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = HttpRequestConfig.model_validate(context.config)
        url = interpolate(config.url, context.variables)
        headers = {k: interpolate(v, context.variables) for k, v in config.headers.items()}
        body = _interpolate_body(config.body, context.variables)

        # A network-level exception (timeout, connection refused, ...) is
        # deliberately left un-caught here, not turned into a Failure -
        # it's exactly the transient class `retryable` exists for (see
        # registry.NodeExecutor.retryable's docstring: only a raised
        # exception gets retried, a returned Failure never does).
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.request(
                config.method,
                url,
                headers=headers,
                json=body if isinstance(body, dict) else None,
                content=body if isinstance(body, str) else None,
            )

        if response.status_code >= 500:
            # A 5xx is plausibly transient too - same reasoning as above.
            response.raise_for_status()
        if response.status_code >= 400:
            # A 4xx is a config/request error, not transient - Failure,
            # not a retried exception.
            return Failure(f"HTTP {response.status_code}: {response.text[:500]}")

        try:
            parsed_body: Any = response.json()
        except ValueError:
            parsed_body = response.text

        return Success(output={"status_code": response.status_code, "body": parsed_body})


node_executor_registry.register(HttpRequestExecutor())
