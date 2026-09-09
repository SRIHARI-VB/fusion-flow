import re

_VALID_TABLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def enable_tenant_rls(op, table_name: str) -> None:
    """Apply the standard tenant-isolation RLS policy to a table.

    Called from Alembic migrations (`op` is the Alembic `Operations`
    object) for every table using `TenantScopedMixin`. Centralising this
    here means the policy SQL is identical for every tenant-scoped table
    instead of being hand-typed (and potentially drifting) per migration.

    `FORCE ROW LEVEL SECURITY` is required in addition to `ENABLE ROW
    LEVEL SECURITY` because table owners bypass RLS by default in
    Postgres - the API's runtime DB role must not be the migration/owner
    role, otherwise this policy would silently not apply to it.
    """
    if not _VALID_TABLE_NAME.match(table_name):
        raise ValueError(f"unsafe table name for RLS DDL: {table_name!r}")

    # No trailing semicolons: Alembic terminates each statement itself, so
    # adding one here renders as `...;;` in `alembic upgrade head --sql`.
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table_name}\n"
        "  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)\n"
        "  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def disable_tenant_rls(op, table_name: str) -> None:
    """Reverse of enable_tenant_rls, for migration downgrades."""
    if not _VALID_TABLE_NAME.match(table_name):
        raise ValueError(f"unsafe table name for RLS DDL: {table_name!r}")

    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
