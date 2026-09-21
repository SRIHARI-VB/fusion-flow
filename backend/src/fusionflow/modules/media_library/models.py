"""`MediaAsset` — a catalog row over media already uploaded through an
existing connector upload endpoint (currently only Cloudflare R2's
`/connectors/{instance_id}/media`, see `connectors/router.py::upload_media`).

This table never drives storage or deletion of the underlying object; it
is purely a listing/index layer. `source` records which connector type
produced the asset (e.g. `"cloudflare_r2"`), so future upload sources can
be added without a schema change beyond a new string value.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class MediaAsset(Base, TenantScopedMixin, TimestampMixin):
    """A single previously-uploaded media object, catalogued for listing."""

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
