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
if [ -n "$POSTGRES_HOST" ] || [ -n "$DATABASE_URL" ]; then
  echo "Applying database migrations with Alembic..."
  alembic upgrade head
  echo "Database migrations applied successfully!"
fi

exec "$@"
