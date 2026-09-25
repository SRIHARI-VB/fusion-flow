"""`/api/v1/users/me` — per-user UI personalization.

Not a tenant entitlement (those live under `modules/connectors/`) - this
is pure per-login preference, scoped to the authenticated user's own
`user_id`. Mounted from `api.py`.
"""

from __future__ import annotations

from fastapi import APIRouter

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.users import service as users_service
from fusionflow.modules.users.schemas import SidebarLayoutEnvelope

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/sidebar-layout", response_model=SidebarLayoutEnvelope)
async def get_sidebar_layout(session: SessionDep, context: TenantContextDep) -> SidebarLayoutEnvelope:
    """Never 404s - "no customization yet" is a normal `{"layout": null}`."""
    layout = await users_service.get_sidebar_layout(session, user_id=context.user.id)
    return SidebarLayoutEnvelope(layout=layout)


@router.put("/me/sidebar-layout", response_model=SidebarLayoutEnvelope)
async def put_sidebar_layout(
    payload: SidebarLayoutEnvelope, session: SessionDep, context: TenantContextDep
) -> SidebarLayoutEnvelope:
    """Upsert the caller's layout. `{"layout": null}` resets to defaults."""
    layout = await users_service.save_sidebar_layout(
        session, tenant_id=context.tenant_id, user_id=context.user.id, layout=payload.layout
    )
    await commit_and_keep_tenant_context(session)
    return SidebarLayoutEnvelope(layout=layout)
