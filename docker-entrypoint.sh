#!/bin/sh
set -e

python manage.py migrate --noinput

if [ "$DEBUG" = "1" ]; then
    exec python manage.py runserver 0.0.0.0:8000
else
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000
fi
