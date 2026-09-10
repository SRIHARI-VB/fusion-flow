-- Runs exactly once, automatically, the first time the postgres container
-- initializes its data volume (official postgres image behavior for every
-- *.sql file under /docker-entrypoint-initdb.d). Executed as POSTGRES_USER
-- ("fusionflow"), which the base image creates as a superuser - so the
-- `ALTER DEFAULT PRIVILEGES` below (no `FOR ROLE` clause) applies to
-- objects that role creates later, which is exactly what alembic does
-- (DATABASE_URL connects as "fusionflow").
--
-- `fusionflow_app` is the low-privilege, non-BYPASSRLS role the running
-- app must query as for RLS to actually apply (see
-- backend/src/fusionflow/config.py::RUNTIME_DATABASE_URL,
-- backend/src/fusionflow/db/rls.py, and the .env.example block this
-- mirrors). Dev-only hardcoded password is fine here - this container
-- only ever listens on localhost.

CREATE ROLE fusionflow_app LOGIN PASSWORD 'fusionflow_app_dev_only'
  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT USAGE ON SCHEMA public TO fusionflow_app;

-- No tables exist yet at first container init (migrations haven't run) -
-- this grants nothing today but documents intent; the ALTER DEFAULT
-- PRIVILEGES below is what actually matters, since it applies
-- retroactively-in-effect to every table `alembic upgrade head` creates
-- afterwards.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fusionflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fusionflow_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fusionflow_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO fusionflow_app;
