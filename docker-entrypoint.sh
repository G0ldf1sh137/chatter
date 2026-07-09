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
    tailwindcss -i ./static/css/input.css -o ./static/css/tailwind.css --minify
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
fi
