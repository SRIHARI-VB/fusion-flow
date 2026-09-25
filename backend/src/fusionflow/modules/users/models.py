"""Per-user UI personalization models.

`UserSidebarLayout` is a pure per-user preference - which sidebar groups/
items a given login has chosen to show, hide, reorder, rename, or
archive. This has nothing to do with tenant *entitlements* (module access,
plan feature flags - those live in `modules/connectors/`): a layout is
scoped to one `user_id` and is never shared across a tenant's other
users.

It still carries `tenant_id` even though the lookup key is always
`user_id`, unique per row (one saved layout per user). That is solely so
`TenantScopedMixin` can apply the same RLS policy every other table in
this app relies on (see `db/rls.py::enable_tenant_rls`) - the app's
runtime DB role has no bypass, so a table with no `tenant_id` column
cannot be queried through it at all once RLS is enabled on the DB.
`tenant_id` is set to whichever business the user has selected at the
time they last saved a layout; it is not itself meaningful to the
frontend contract.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class UserSidebarLayout(Base, TenantScopedMixin, TimestampMixin):
    """One user's saved sidebar customization.

    `layout` is nullable: NULL means "this user has never saved a
    customization" - a normal, expected state, not an error - and the
    frontend should render its built-in default layout. See
    `modules/users/schemas.py::SidebarLayout` for the validated JSON shape
    stored here.
    """

    __tablename__ = "user_sidebar_layouts"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    layout: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
