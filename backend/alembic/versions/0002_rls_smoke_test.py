"""Throwaway tenant-scoped table used to prove the RLS mechanism.

Revision ID: 0002_rls_smoke_test
Revises: 0001_initial
Create Date: 2026-09-09

WHY THIS EXISTS — Wave 0 ships the RLS *machinery* (`db/rls.py`,
`TenantScopedMixin`, `set_tenant_context`) but no real tenant-scoped domain
table yet; those arrive in Wave 1 (products, orders, tickets, connector
instances, ...). Without at least one policy-bearing table there is nothing
to point an isolation test at, and an untested isolation mechanism is worth
very little.

`_rls_smoke_test` is therefore a deliberately minimal table (id, tenant_id,
label) whose only job is to let `backend/tests/test_rls_isolation.py` prove
that Postgres itself - not Python filtering - enforces the boundary.

DROP THIS TABLE (and this migration's table, via a new migration) as soon as
a real tenant-scoped table exists: re-point the isolation test at that table
first, then remove `_rls_smoke_test`. The leading underscore marks it as
non-domain so it is easy to spot.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from fusionflow.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0002_rls_smoke_test"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "_rls_smoke_test"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["businesses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix__rls_smoke_test_tenant_id", TABLE_NAME, ["tenant_id"])

    # The one line every future tenant-scoped table's migration must also
    # carry. Emits ENABLE + FORCE ROW LEVEL SECURITY and the
    # `tenant_isolation` policy keyed on app.current_tenant_id.
    enable_tenant_rls(op, TABLE_NAME)


def downgrade() -> None:
    disable_tenant_rls(op, TABLE_NAME)
    op.drop_index("ix__rls_smoke_test_tenant_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
