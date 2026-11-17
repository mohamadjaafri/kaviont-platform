#!/bin/sh
set -eu

: "${PGHOST:=postgres}"
: "${PGUSER:=kaviont}"
: "${PGPASSWORD:=kaviont-local-only}"
: "${PGDATABASE:=postgres}"
: "${POSTGRES_EXPORTER_PASSWORD:?POSTGRES_EXPORTER_PASSWORD must be set}"

export PGHOST PGUSER PGPASSWORD PGDATABASE

psql --no-psqlrc --set ON_ERROR_STOP=1 --set exporter_password="${POSTGRES_EXPORTER_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE postgres_exporter LOGIN PASSWORD %L', :'exporter_password')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = 'postgres_exporter'
)
\gexec

ALTER ROLE postgres_exporter WITH LOGIN PASSWORD :'exporter_password';
ALTER ROLE postgres_exporter SET search_path TO postgres_exporter, pg_catalog;
GRANT CONNECT ON DATABASE postgres TO postgres_exporter;
GRANT pg_monitor TO postgres_exporter;
SQL
