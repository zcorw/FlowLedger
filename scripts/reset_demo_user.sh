#!/bin/sh
set -e

if [ -z "$POSTGRES_DB" ] || [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ]; then
  echo "Missing POSTGRES_* env vars." >&2
  exit 1
fi

PGHOST=${PGHOST:-db}
PGPORT=${PGPORT:-5432}

export PGPASSWORD="$POSTGRES_PASSWORD"

psql -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /work/scripts/reset_demo_user.sql
