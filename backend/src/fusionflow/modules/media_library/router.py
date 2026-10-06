"""`/media-assets` — a read-only catalog over media already uploaded
through an existing connector upload endpoint (see
`connectors/router.py::upload_media`, which is the sole write path for
this table).

Not mounted here — see other routers' docstrings for the same convention;
the integration wave mounts `router` from this module.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.modules.connectors.deps import require_module_access
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.media_library import service as media_library_service
from fusionflow.modules.media_library.schemas import MediaAssetOut

router = APIRouter(prefix="/media-assets", tags=["media-library"], dependencies=[Depends(require_module_access("communication"))])


@router.get("", response_model=list[MediaAssetOut])
async def list_media_assets(session: SessionDep, context: TenantContextDep) -> list[MediaAssetOut]:
    media_assets = await media_library_service.list_media_assets(session, tenant_id=context.tenant_id)
    return [MediaAssetOut.model_validate(media_asset) for media_asset in media_assets]


@router.delete("/{media_asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_asset(
    media_asset_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> None:
    media_asset = await media_library_service.get_media_asset(
        session, tenant_id=context.tenant_id, media_asset_id=media_asset_id
    )
    if media_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    await media_library_service.delete_media_asset(session, media_asset)
    await commit_and_keep_tenant_context(session)
