#!/bin/sh
set -eu

: "${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY is required}"
: "${DJANGO_ALLOWED_HOSTS:?DJANGO_ALLOWED_HOSTS is required}"

if [ "${PATHPLANNER_ENSURE_LOCAL_OSM_DB:-false}" = "true" ] || [ "${PATHPLANNER_ENSURE_LOCAL_OSM_DB:-false}" = "1" ]; then
  python scripts/ensure_local_osm_poi_db.py
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
