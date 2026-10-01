#!/bin/sh
set -e

if [ -n "$POSTGRES_HOST" ]; then
  echo "Waiting for PostgreSQL at $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
  while ! nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}"; do
    sleep 0.5
  done
  echo "PostgreSQL is ready!"
fi

if [ -n "$REDIS_HOST" ]; then
  echo "Waiting for Redis at $REDIS_HOST:${REDIS_PORT:-6379}..."
  while ! nc -z "$REDIS_HOST" "${REDIS_PORT:-6379}"; do
    sleep 0.5
  done
  echo "Redis is ready!"
fi

# Run database migrations automatically
echo "Applying database migrations with Alembic..."
alembic upgrade head || echo "Alembic migrations skipped or already up to date"

# Run database seed if requested
if [ "$SEED_DB" = "true" ] || [ "$AUTO_SEED" = "true" ]; then
  echo "Auto-seeding initial database records..."
  python -m app.db.seed || echo "Seed skipped or already initialized"
fi

exec "$@"
