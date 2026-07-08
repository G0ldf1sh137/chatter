#!/bin/sh
set -e

cd "$(dirname "$0")/.."

echo "==> Building images"
docker compose build

echo "==> Starting database"
docker compose up -d db

echo "==> Waiting for database to be healthy"
until [ "$(docker compose ps -q db | xargs docker inspect -f '{{.State.Health.Status}}')" = "healthy" ]; do
    sleep 1
done

echo "==> Running migrations"
docker compose run --rm web python manage.py migrate --noinput

echo "==> Running tests"
docker compose run --rm web python manage.py test

echo "==> Running deploy checks"
docker compose run --rm -e DEBUG=0 web python manage.py check --deploy

echo "==> Build and test succeeded"
