#!/bin/sh
set -e

# Apply migrations (this also loads the study content on a fresh database).
python manage.py migrate --noinput

exec "$@"
