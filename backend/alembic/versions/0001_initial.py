"""Initial platform schema: users, businesses, memberships, refresh_tokens.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09

RLS NOTE — none of the four tables created here get a row-level-security
policy, and that is deliberate:

* `users`      — one identity can belong to many businesses, so there is no
                 single tenant_id to filter on.
* `businesses` — this *is* the tenant registry; `TenantScopedMixin.tenant_id`
                 references `businesses.id`, so it cannot filter on its own
                 tenant.
* `refresh_tokens` — read during login/refresh, before any tenant context
                 exists; a policy here would make login impossible.
* `memberships` — the judgment call. It carries a `business_id` and so
                 *looks* tenant-scoped, but it is read precisely during the
                 auth and business-switch flows that run **before**
                 `SET LOCAL app.current_tenant_id` has been set. Putting it
                 under RLS would mean login could never discover which
                 businesses a user belongs to (the query would return zero
                 rows and the user would be locked out). It therefore stays
                 a platform table alongside users/businesses/refresh_tokens,
                 matching the plan's "platform tables are not
                 tenant-RLS-scoped" rule. Its isolation guarantee comes from
                 application code instead: every query against `memberships`
                 filters on the authenticated `user_id` (see
                 modules/tenancy/service.py) and no route exposes another
                 user's memberships.

Tenant-scoped domain tables arrive in later waves and MUST call
`fusionflow.db.rls.enable_tenant_rls(op, "<table>")` in their migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


membership_role = postgresql.ENUM(
    "owner", "admin", "member", "viewer", name="membership_role", create_type=False
)
business_status = postgresql.ENUM(
    "active", "suspended", name="business_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    # checkfirst=True keeps this idempotent if a partially-applied database
    # already has the type.
    membership_role.create(bind, checkfirst=True)
    business_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("vertical", sa.String(length=80), nullable=True),
        sa.Column(
            "status", business_status, nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_businesses_slug", "businesses", ["slug"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        sa.Column(
            "invited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "business_id", name="uq_membership_user_business"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_business_id", "memberships", ["business_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # sha256 hex digest of the opaque token - the raw value is never stored.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NULL for a pre-tenant (identity-only) session.
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    # Family revocation on reuse detection scans by family_id.
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_memberships_business_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_businesses_slug", table_name="businesses")
    op.drop_table("businesses")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    business_status.drop(bind, checkfirst=True)
    membership_role.drop(bind, checkfirst=True)
