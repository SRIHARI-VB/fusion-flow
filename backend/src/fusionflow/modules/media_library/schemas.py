"""Pydantic schemas for `/media-assets`.

No `Create` schema: rows are created only as a side effect of the
existing connector upload endpoint (`connectors/router.py::upload_media`),
never via a direct POST to this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    filename: str
    content_type: str
    size_bytes: int
    source: str
    created_at: datetime
