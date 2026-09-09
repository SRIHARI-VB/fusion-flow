"""Fix tenant_isolation policy predicate: NULLIF the empty-string GUC case.

Revision ID: 0004_fix_rls_null_tenant_context
Revises: 0003_wave1_domain_tables
Create Date: 2026-09-09

Found by actually running `backend/tests/test_rls_isolation.py` against a
live Postgres (Supabase) for the first time: once `SET LOCAL
app.current_tenant_id` has been used at all on a physical connection,
Postgres reverts the custom GUC to `''` (empty string) - not NULL - once
that transaction ends. `current_setting(..., true)::uuid` then throws
`invalid_text_representation` on the empty string instead of the policy
evaluating to NULL/false, so a request that forgets to set tenant context
on an already-used pooled connection gets a 500 error instead of the
intended fail-safe (zero rows, no leak) - the exact connection-pooling
scenario Risk #2 in the architecture plan warned about, just manifesting
as an error rather than a silent leak.

`db/rls.py::enable_tenant_rls` is fixed for any *new* table going forward
(NULLIF wraps the cast); this migration applies the same fix via
`ALTER POLICY` to every policy that migration 0002/0003 already created
on a real database, since `enable_tenant_rls` cannot be re-run against a
table that already has a `tenant_isolation` policy (CREATE POLICY would
fail on the duplicate name).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_fix_rls_null_tenant_context"
down_revision: Union[str, None] = "0003_wave1_domain_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table that has ever had `enable_tenant_rls` applied by a prior
# migration: the 20 Wave 1 tenant-scoped tables plus the Wave 0 smoke-test
# table.
RLS_TABLES = [
    "_rls_smoke_test",
    "connector_instances",
    "connector_credentials",
    "connector_events",
    "connector_oauth_states",
    "field_definitions",
    "products_services",
    "coupons",
    "offers",
    "customers",
    "orders",
    "payments",
    "tickets",
    "ticket_messages",
    "kb_articles",
    "workflows",
    "workflow_versions",
    "workflow_runs",
    "workflow_run_steps",
    "workflow_triggers",
    "workflow_trigger_inbox",
]


def upgrade() -> None:
    for table_name in RLS_TABLES:
        op.execute(
            f"ALTER POLICY tenant_isolation ON {table_name}\n"
            "  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)\n"
            "  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table_name in RLS_TABLES:
        op.execute(
            f"ALTER POLICY tenant_isolation ON {table_name}\n"
            "  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)\n"
            "  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        )
