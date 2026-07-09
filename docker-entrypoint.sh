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
    exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
fi
