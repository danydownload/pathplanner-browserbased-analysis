# Local routing engine option

The app can optionally use a GraphHopper-compatible routing service before the
Overpass street-graph A* path.

Why this exists:

- Public Overpass is real OSM data, but it is shared infrastructure and can time
  out under bbox-heavy route requests.
- A local GraphHopper instance uses real OSM extracts too, but keeps the routing
  graph local and predictable for demos.
- The app still owns the clinical/environmental scoring. GraphHopper supplies
  candidate routes; PathPlanner ranks them using patient weights, real
  air-quality/weather/elevation samples, and real OSM POIs when available.

Configuration:

```env
GRAPHHOPPER_URL=http://host.docker.internal:8989
GRAPHHOPPER_TIMEOUT_SECONDS=8
GRAPHHOPPER_FORCE=false
GRAPHHOPPER_PROFILE_WALKING=foot
GRAPHHOPPER_PROFILE_CYCLING=bike
GRAPHHOPPER_PROFILE_CAR=car
```

Behavior:

- If `GRAPHHOPPER_URL` is empty, nothing changes: the backend uses Overpass
  street-graph A*.
- If `GRAPHHOPPER_URL` is set and returns route alternatives, those real OSM
  route candidates are used and scored.
- If GraphHopper is set but unavailable, the backend falls back to Overpass A*
  unless `GRAPHHOPPER_FORCE=true`.
- If `GRAPHHOPPER_FORCE=true` and GraphHopper cannot return usable routes, the
  endpoint returns a service error instead of silently using Overpass.

This is not a city cache. The routing graph comes from an OSM extract chosen for
the demo/runtime, and the app still works with any city covered by that extract.
