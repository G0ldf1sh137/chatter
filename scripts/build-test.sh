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
# RENDER=true simulates actually being deployed on Render (not just DEBUG=0),
# since SSL-redirect/HSTS settings are deliberately scoped to that signal -
# see config/settings.py's IS_RENDER. The SECRET_KEY warning below is
# expected locally (.env's placeholder isn't a real secret) - a real
# deployment gets a proper one via render.yaml's generateValue.
docker compose run --rm -e DEBUG=0 -e RENDER=true web python manage.py check --deploy

echo "==> Build and test succeeded"
