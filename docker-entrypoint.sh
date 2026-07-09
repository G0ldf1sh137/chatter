#!/bin/sh
set -e

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

python manage.py migrate --noinput

if [ "$DEBUG" = "1" ]; then
    tailwindcss -i ./static/css/input.css -o ./static/css/tailwind.css --watch &
    exec python manage.py runserver 0.0.0.0:8000
else
    # No tailwindcss/collectstatic here - both are baked into the image at
    # build time (see Dockerfile), so a container restart doesn't redo them.
    # --no-control-socket: gunicorn's runtime-management socket (for the
    # gunicornc CLI, which nothing here uses) defaults to $HOME/.gunicorn/,
    # but the "app" user is a homeless system account (useradd -r), so it
    # fails with a "Permission denied: '/home/app'" error on every start -
    # harmless (HTTP serving is unaffected) but disabled since it's unused.
    exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --no-control-socket
fi
