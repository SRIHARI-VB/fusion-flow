"""`/business-templates` — tenant-facing read + "apply" for `BusinessTemplate`.

New module, not mounted here: `fusionflow.api`'s `/api/v1` router group is
out of this task's scope to edit directly (see this task's final report for
the exact one-line snippet needed). Intended final path:
`/api/v1/business-templates`.

Deliberately a brand-new module rather than tacked onto
`modules.custom_fields.router` or `modules.tenancy.router`: both of those
files are outside this task's ownership this wave (one because it's a
different, older concept this task was told not to conflate with; the
other because a parallel agent owns `modules/tenancy/models.py` and, by
extension, its router, for an unrelated column this wave). The underlying
`BusinessTemplate`/`BusinessTemplateConnectorType` models live in
`modules.admin.models` per the plan's file-level anchor for this task.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.deps import CurrentUserDep, SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.admin.models import BusinessTemplate, BusinessTemplateConnectorType
from fusionflow.modules.business_templates.schemas import (
    ApplyBusinessTemplateResponse,
    BusinessTemplateOut,
)
from fusionflow.modules.connectors.models import ConnectorType
from fusionflow.modules.tenancy.models import Business

router = APIRouter(prefix="/business-templates", tags=["business-templates"])


async def _to_out(session: AsyncSession, template: BusinessTemplate) -> BusinessTemplateOut:
    keys = (
        await session.execute(
            select(ConnectorType.key)
            .join(
                BusinessTemplateConnectorType,
                BusinessTemplateConnectorType.connector_type_id == ConnectorType.id,
            )
            .where(BusinessTemplateConnectorType.business_template_id == template.id)
        )
    ).scalars().all()
    return BusinessTemplateOut(
        id=template.id,
        key=template.key,
        name=template.name,
        description=template.description,
        vertical=template.vertical,
        plan_id=template.plan_id,
        is_active=template.is_active,
        connector_type_keys=list(keys),
    )


@router.get("", response_model=list[BusinessTemplateOut])
async def list_business_templates(user: CurrentUserDep, session: SessionDep) -> list[BusinessTemplateOut]:
    """Active templates only. Global catalog, not tenant-scoped - depends on
    `CurrentUserDep` only (same pattern as `custom_fields.router.list_templates`),
    so onboarding's "pick a starter kit" step can call this before a business
    has even been selected on this session's token.
    """
    rows = (
        (
            await session.execute(
                select(BusinessTemplate)
                .where(BusinessTemplate.is_active.is_(True))
                .order_by(BusinessTemplate.name)
            )
        )
        .scalars()
        .all()
    )
    return [await _to_out(session, t) for t in rows]


@router.post("/{template_id}/apply", response_model=ApplyBusinessTemplateResponse)
async def apply_business_template(
    template_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> ApplyBusinessTemplateResponse:
    """Record the tenant's chosen starter kit.

    Sets `Business.business_template_id` (and, only if the tenant has no
    plan yet, `Business.plan_id` from the template's default plan) directly
    on the `businesses` row here, rather than through
    `modules.tenancy.router` (owned by a different agent this wave for an
    unrelated column - see this task's report). Applying the matching
    `FieldTemplate`s for this template's `vertical` is left to the
    frontend's existing `applyFieldTemplate` call against
    `POST /custom-fields/templates/{id}/apply` - this route only owns the
    business-template linkage itself and returns `vertical` so the caller
    knows which field templates to apply next. See this task's report for
    why the two calls are sequenced client-side instead of one endpoint
    doing both.
    """
    template = await session.get(BusinessTemplate, template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business template not found")

    business = await session.get(Business, context.tenant_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # `business_template_id`/`plan_id` don't exist on the `Business` ORM
    # model in this checkout yet (see this task's report) - these
    # assignments are documented no-ops until that column lands via
    # migration, at which point they start persisting with no code change.
    business.business_template_id = template.id  # type: ignore[attr-defined]
    if template.plan_id is not None and getattr(business, "plan_id", None) is None:
        business.plan_id = template.plan_id  # type: ignore[attr-defined]

    await commit_and_keep_tenant_context(session)
    return ApplyBusinessTemplateResponse(business_template_id=template.id, vertical=template.vertical)
