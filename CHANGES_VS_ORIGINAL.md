# CHANGES vs ORIGINAL — PathPlanner (Browser-based Analysis)

This document inventories **every meaningful difference** between the original
downloaded baseline and the current working repository, grouped by area. Every
entry below is grounded in a real file-level diff (see *Verification method*),
not guesswork.

| | |
|---|---|
| **ORIGINAL (baseline)** | `/Users/dtortoli/Downloads/pathplanner_browserbased_analysis (1)` |
| **CURRENT (this repo)**  | `/Users/dtortoli/Code/pathplanner_browserbased_analysis` |
| **Date produced** | 2026-06-23 |
| **Method** | `diff -rq` (recursive, excluding `.git`, `__pycache__`, `node_modules`, `.venv*`, `.worktrees`, `staticfiles`, `*.sqlite3`, `.env`) + per-file unified diffs |
| **Authors** | `claude-pp-diff` (backend / A* algorithm) · `codex-pp-diff` (frontend / config-infra) — cross-verified, two independent runtimes |

---

## 1. Executive summary

The current version turns the original "environmental routing demo" into a
**health-aware, real-data routing application that is production-deployable**.
The change set is coherent along three axes:

1. **Pathology- & preference-aware routing on REAL environmental data.**
   The A* cost model (both the Python backend and the JavaScript frontend) now
   factors per-pathology *and* per-user preference weights, plus proximity to
   **real** points of interest (parks, hospitals) pulled from the database and
   OpenStreetMap. Two new API endpoints (`/api/environment`, `/api/pois`) expose
   **genuine** air-quality / pollen / POI data sourced from Open-Meteo, OpenAQ
   and Overpass — never synthetic.

2. **Complete UI/UX redesign.** A new design-system stylesheet (`theme.css`)
   plus a fully rebuilt map "app shell": collapsible route sidebar, clinical
   routing-profile selector, right-hand environmental drawer, detached
   turn-by-turn directions panel, route preview/animation, on-route POI lists,
   and real-vs-synthetic data badges. Geocoding moved from LocationIQ to Mapbox.

3. **Production readiness.** New Docker/Compose/Nginx/systemd deploy stack,
   `core/settings.py` made fully environment-driven with production security
   flags, pinned `requirements.txt` plus `gunicorn`, and a Linux/Docker
   deployment guide.

A notable cross-cutting **security improvement**: the Mapbox access token, which
was **hard-coded** in client JavaScript in the original, is now externalized to
`window.MAPBOX_ACCESS_TOKEN` (injected server-side), and the Django
`SECRET_KEY` / `DEBUG` / `ALLOWED_HOSTS` are read from the environment with a
hard failure in production if unset.

No files were **deleted** between baseline and current; the delta is additions
and modifications only.

---

## 2. Change inventory

Status legend: **NEW** = added in current · **MOD** = modified · counts are
`+added/-removed` lines from `diff`.

### 2.1 Backend & A* (Python / Django)

| File | Status | Detail |
|---|---|---|
| `evaluations/environmental_astar.py` | MOD (+236/-1) | POI-based preference routing; 5 new patient dimensions + `default` profile |
| `evaluations/real_environment_service.py` | **NEW** (492) | Real air-quality/pollen service (Open-Meteo + OpenAQ v3) |
| `evaluations/environmental_data_service.py` | MOD (+118) | `fetch_named_pois()` (Overpass parks/hospitals) + 3rd Overpass mirror |
| `evaluations/views.py` | MOD (+169/-7) | New `/api/environment` & `/api/pois` views; preference extraction |
| `evaluations/urls.py` | MOD (+7/-1) | Routes for `/environment` and `/pois` (+ no-slash aliases) |
| `evaluations/tests.py` | MOD (+120/-2) | New tests for `/api/environment` (mocked Open-Meteo + OpenAQ) |
| `core/settings.py` | MOD (~+70) | Env-driven config + security hardening + static/media/sqlite paths |
| `core/views.py` | MOD | Passes `default_pathology` + `mapbox_access_token` to the map template |
| `users/models.py` | MOD (+17) | New `default_pathology` field + `PATHOLOGY_CHOICES` |
| `users/migrations/0024_userprofile_default_pathology.py` | **NEW** | Migration for `default_pathology` |
| `users/forms.py` | MOD (+20/-7) | Profile form: `default_pathology` (RadioSelect) replaces profile picture |
| `users/views.py` | MOD (+24/-3) | `?next=` honored on login; profile↔User sync; `LoginRequiredMixin` |
| `users/signals.py` | MOD (+6/-1) | Copy first/last name & email into profile on creation |
| `scripts/benchmark_poi_precompute.py` | **NEW** | Benchmark: sequential vs parallel POI precompute |
| `scripts/test_astar_perf.py` | **NEW** | Playwright A* performance probe |

### 2.2 Frontend (templates / CSS / JS)

| File | Status | Detail |
|---|---|---|
| `templates/map.html` | MOD (+190/-73) | Rebuilt map "app shell"; wires `theme.css`, new JS modules, Mapbox token |
| `templates/homePage.html` | MOD (+48/-38) | Redesigned to `theme.css` / responsive |
| `templates/404.html` | MOD (+17/-15) | Redesigned error page |
| `templates/not_authorized.html` | MOD (+17/-15) | Redesigned 403 page |
| `static/css/theme.css` | **NEW** (95) | Design-system tokens (colors, radii, shadows, typography, dark mode) |
| `static/css/map.css` | MOD (+2316/-68) | Largest UI diff: full map shell, sidebar, cards, drawer, badges, mobile |
| `static/css/usersTemplates.css` | MOD (+340/-29) | Token-driven user pages |
| `static/css/preferences.css` | MOD (+142/-28) | Redesigned preferences UI |
| `static/css/homePage.css` | MOD (+119/-18) | Redesigned home |
| `static/css/suggestions.css` | MOD (+69/-73) | Redesigned autocomplete UI |
| `static/css/errorPage.css` | MOD (+53/-13) | Redesigned error pages |
| `static/js/master/routes.js` | MOD (+2320/-645) | Route presentation/comparison, POI panel, directions, preview, badges |
| `static/js/algorithms/environmentalAStar.js` | MOD (+494/-105) | Frontend A* with preference weights + POI proximity + real-env seed |
| `static/js/services/routePlanner.js` | MOD (+298/-74) | Preference-aware planning, nonblocking env prefetch, synthetic flags |
| `static/js/suggestions.js` | MOD (+284/-45) | LocationIQ → Mapbox Searchbox geocoding |
| `static/js/heatmap.js` | MOD (+161/-96) | Registered layer IDs, multi-layer state, pollen demo layer |
| `static/js/map.js` | MOD (+158/-0) | Sidebar/drawer/directions behavior, ARIA, `invalidateSize()` |
| `static/js/services/environmental.js` | MOD (+51/-5) | Concurrent post-route env sampling, fallback flags |
| `static/js/routing.js` | MOD (+31/-549) | Removes old debug/`#options` path; persisted `pp_legacyMode` |
| `static/js/location.js` | MOD (+26/-0) | Geolocation feeds the environmental inspector |
| `static/js/services/elevation.js` | MOD (+2/-2) | Mapbox token externalized to `window.MAPBOX_ACCESS_TOKEN` |
| `static/js/benchmark/benchmarkRunner.js` | MOD (+1/-2) | Mapbox token externalized |
| `static/js/environmentInspector.js` | **NEW** (561) | Right-drawer real air-quality/pollen inspector (`/api/environment`) |
| `static/js/routeStepSimulator.js` | **NEW** (734) | Animated route preview / turn-by-turn cursor |
| `static/js/services/poisAlongRoute.js` | **NEW** (270) | Real `/api/pois` POIs near a route (no synthetic data) |
| `static/js/utils/envQualityBadge.js` | **NEW** (244) | Non-blocking env-quality badge (anti-stale render tokens) |
| `users/templates/edit_profile.html` | MOD (+50/-10) | Default clinical condition as radio-card UI |
| `users/templates/profile.html` | MOD (+34/-18) | Responsive profile/preferences dashboard |
| `users/templates/basePreferences.html` | MOD (+12/-1) | Redesign |
| `users/templates/baseUser.html` | MOD (+11/-1) | Preserves `next` via hidden input |
| `users/templates/login.html` | MOD (+6/-4) | Redesign / grouped actions |
| `users/templates/signup.html` | MOD (+6/-4) | Redesign / grouped actions |
| `users/templates/edit_preferences.html` | MOD (+3/-1) | Redesign |
| `users/templates/add_preferences.html` | MOD (+3/-1) | Redesign |

### 2.3 Config / Infra / Deploy

| File | Status | Detail |
|---|---|---|
| `Dockerfile` | **NEW** | Python 3.12-slim, non-root, Gunicorn entrypoint |
| `docker-compose.yml` | **NEW** | `app` (Gunicorn) + `nginx` services, named volumes, healthcheck |
| `docker/entrypoint.sh` | **NEW** | Requires secret/hosts; runs migrate + collectstatic |
| `.dockerignore` | **NEW** | Excludes git/venv/sqlite/backups/env/logs/artifacts from image |
| `.env.example` | **NEW** | Documents required production env vars |
| `.gitignore` | **NEW** | Ignores `.env*` (keeps `.env.example`), sqlite, venvs, logs, artifacts |
| `deploy/nginx/pathplanner-docker.conf` | **NEW** | Nginx reverse proxy for Compose (`app:8000`) |
| `deploy/nginx/pathplanner-systemd.conf` | **NEW** | Nginx config for non-Docker Gunicorn |
| `deploy/systemd/pathplanner-docker.service` | **NEW** | systemd unit: `docker compose up -d` |
| `deploy/systemd/pathplanner-gunicorn.service` | **NEW** | systemd unit: non-Docker Gunicorn |
| `requirements.txt` | MOD | Pinned versions + added `gunicorn==23.0.0` |

### 2.4 Documentation & analysis (new, current-only)

| File | Status | Detail |
|---|---|---|
| `docs/deployment-linux-docker.md` | **NEW** | Linux/Docker deployment guide (IT) |
| `docs/A_STAR_TRAFFIC_OPENMAP.md` | **NEW** | Traffic-data / OSRM / Valhalla options analysis |
| `A_STAR_ANALYSIS.md` | **NEW** | A* algorithm analysis (root) |
| `REPO_ANALYSIS.md` | **NEW** | Repository analysis (root) |

### 2.5 QA / proof assets (new, not runtime code)

| Path | Status | Detail |
|---|---|---|
| `tests/playwright/*` | **NEW** | E2E specs: sidebar, directions card, environment inspector, suggestions, routing label, POI/badge proof harnesses |
| `tests/perf/*` | **NEW** | `envQualityBadge.proof.mjs`, `poisAlongRouteAvailability.proof.mjs` |

> ⚠️ These are **added** QA assets. Their pass/fail status is **not asserted**
> here — at least one spec (`environment-inspector.spec.js`) still references
> legacy selectors (`#envInspectorToggle`) that the current UI renamed
> (`#rightSidebarToggle`), so the suite would need a rerun/update before being
> cited as green.

### 2.6 Generated artifacts / backups / noise (excluded from functional changes)

These differ between trees but are **not** functional source changes:
`artifacts/` (QA screenshots), `logs/`, `runserver.log`, `test-results/`,
`uploads/`, `db.sqlite3.bak-pp2`, `.DS_Store`, and editor backups
(`templates/map.html.bak`, `templates/map.html.bak-clientdiag`,
`static/js/routing.js.bak`, `static/js/routing.js.bak2`,
`static/js/master/routes.js.bak-clientdiag`,
`static/js/master/routes.js.bak-clientdiag2`).

---

## 3. Backend & A* algorithm — detail

### 3.1 `evaluations/environmental_astar.py` (+236/-1) — the core change

- **New preference dimensions.** Every pathology profile (`respiratory`,
  `cardiac`, `mobility`, `mental`, `arthritis`, `diabetes`) gains five fields:
  `patientNature`, `patientEntertainment`, `patientNightlife`, `patientTourism`,
  `patientHospital`. A new neutral **`default`** profile (all zeros) is added.
- **Real POI system.** New helpers query the database for real POIs inside the
  search-grid bounding box — `Hospital` rows and `Stazione` rows tagged
  `nature` / `entertainment` / `tourism` / `nightlife`
  (`get_poi_lists_for_grid`). POIs are bucketed into a lat/lon **spatial index**
  (`build_poi_spatial_index`, ~200 m cells), and nearest-POI distances are
  **precomputed per grid node** (`precompute_poi_distances`,
  `nearest_poi_distance_indexed`).
- **Cost model.** `calculate_edge_cost` now accepts `preferences`, `poi_lists`
  and `poi_distances`. It combines pathology weights **+** user preference
  weights, applied both as environmental proxies (greenVisibility / noise /
  emergencyAccessibility) and as a **real POI-distance reward/penalty** with
  exponential decay (`PREFERENCE_POI_DECAY_M = 200.0`,
  `PREFERENCE_POI_SCALE = 5.0`).
- `environmental_astar()` / `find_optimal_route()` accept a `preferences` dict
  and build the POI lists/distances before the search loop.

### 3.2 `evaluations/real_environment_service.py` (NEW, 492 lines)

Real, non-synthetic environmental data service:

- **Open-Meteo Air Quality API** for 14 pollutant/pollen variables
  (european/us AQI, PM10, PM2.5, CO, NO₂, SO₂, O₃, and 6 pollen species).
- **OpenAQ v3** nearest-station observations (uses `OPENAQ_API_KEY`, 25 km
  radius, up to 5 locations).
- 15-minute cache, pathology aliasing (IT/EN synonyms → canonical), per-waypoint
  payloads (`build_environment_payload`), `clear_environment_cache()` for tests.

### 3.3 `evaluations/environmental_data_service.py` (+118)

- `fetch_named_pois()` — real OSM POIs via Overpass for two categories
  (`parks`, `hospitals`); returns only genuine OSM elements (name may be
  `null`), dedups by name, guards against >25 km bounding boxes, and caches.
- Adds a **third Overpass mirror** for resilience.

### 3.4 `evaluations/views.py` (+169/-7) & `urls.py`

- **`get_real_environment_data`** → `/api/environment` (GET + POST,
  `@csrf_exempt`): parses `lat/lon` or `waypoints` + `pathologies`, returns the
  real-environment payload; validates coordinate ranges.
- **`get_pois_in_bbox`** → `/api/pois`: returns real OSM POIs of a category in a
  bbox.
- **`_extract_preferences`** reads `nature/entertainment/tourism/nightlife/`
  `hospital` from GET params or JSON body and threads them through
  `compute_astar_optimized_route`, `optimized_route` and `astar_route`.

### 3.5 Users app (profile gains a clinical default)

- `models.py`: new `default_pathology` `CharField` (choices `PATHOLOGY_CHOICES`,
  default `none`) + migration `0024_userprofile_default_pathology.py`.
- `forms.py`: profile form now edits `default_pathology` (rendered as
  `RadioSelect`) and drops the profile-picture field; adds placeholders.
- `views.py`: login honors `?next=`; `EditProfileView` syncs the Django `User`
  (first/last name, email) with the profile and uses `LoginRequiredMixin`;
  `get_initial` seeds the form from the user account.
- `signals.py`: profile creation now copies the user's name/email.

### 3.6 `core/settings.py` & `core/views.py`

- `settings.py`: local `.env` loader + `env_bool` / `env_int` / `env_list`
  helpers; `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
  `MAPBOX_ACCESS_TOKEN`, `OPENAQ_API_KEY` become environment-driven (production
  without secret/hosts raises `ImproperlyConfigured`); adds
  `SECURE_PROXY_SSL_HEADER`, optional SSL redirect, secure session/CSRF cookies,
  HSTS options, `LOGIN_URL`, `STATIC_ROOT`, `MEDIA_URL`/`MEDIA_ROOT`, and a
  `DJANGO_SQLITE_PATH` override.
- `views.py`: `MapView` passes `default_pathology` and `mapbox_access_token`
  into the map template context.

---

## 4. Frontend (templates / CSS / JS) — detail

*Verified by `codex-pp-diff`; cross-checked against the file-level diffs.*

### 4.1 Map page & design system

- `templates/map.html` + `core/views.py`: the map page goes from a simple
  Bootstrap sidebar/map to a full **app shell** — loads `theme.css`, injects
  `window.MAPBOX_ACCESS_TOKEN`, receives `default_pathology` /
  `mapbox_access_token` from the view, and wires `routeStepSimulator.js` +
  `environmentInspector.js`. New UI: collapsible left route sidebar,
  no-saved-preferences state with a create link, clinical routing-profile
  selector (defaulted from the user profile), persisted **legacy-mode toggle**,
  layer chips incl. `pollen`, user menu with a pathology-preferences link,
  right environmental drawer, and a detached turn-by-turn directions panel.
- `static/css/theme.css` (NEW): shared design tokens (colors, radii, shadows,
  typography, dark-mode variables).
- `static/css/map.css` (+2316/-68): the largest UI diff — styles the whole
  shell, sidebar collapse, route/directions cards, preview cursor, right
  environmental drawer, AQI/metric cards, on-route POI lists, real/synthetic
  badges, pollen/layer chips, and responsive/mobile states.
- `homePage.css`, `errorPage.css`, `preferences.css`, `suggestions.css`,
  `usersTemplates.css`: rewritten from the old orange/radial-gradient/inline
  look into token-driven responsive layouts.

### 4.2 Map behavior & geocoding

- `static/js/map.js`: collapsible route controls, right environmental sidebar,
  floating directions panel; ARIA state, focus handling / `inert` fallback,
  Escape-to-close, repeated `map.invalidateSize()` during transitions.
- `static/js/suggestions.js`: **LocationIQ → Mapbox Searchbox** (suggest /
  retrieve / reverse). Uses `window.MAPBOX_ACCESS_TOKEN`, per-input session
  tokens, debounced request IDs (anti-stale), accessible button rows, and
  geolocation reverse lookup. *(Verified: original had 2 `locationiq`
  references; current has 0 and 21 `mapbox` references.)*
- `static/js/location.js` + new `environmentInspector.js`: geolocation feeds the
  inspector (`pathplanner:geolocation-position` →
  `loadForCoordinates`), which fetches `/api/environment`, groups metrics by
  pathology, renders AQI + metric cards with source/timestamp, labels real data
  `REALE` and missing values `N/D`, aborts stale fetches, and reloads when the
  drawer opens.
- `static/js/heatmap.js`: pollutant heat layers refactored to registered layer
  IDs with multi-layer active state + marker-cluster sync; adds a **pollen demo
  layer** (PM10/PM2.5/NO₂/O₃ still from `/api/stazioni_dati/`; pollen is
  client-side demo data).

### 4.3 Routing, comparison & preview

- `static/js/routing.js`: removes the old debug/download-button mutation block
  and `#options` route path; adds persisted `pp_legacyMode`; optimized routing
  is chosen only for patient mode or explicit legacy mode; passes
  `{ preferAStar, legacy }` + preferences to
  `RoutePlanner.generateOptimizedRoutes`. CSV export retained via the redesigned
  menu.
- `static/js/master/routes.js` (+2320/-645): major expansion of route
  presentation/comparison — Mapbox router token from page config, route styling
  & dedup, **user-facing route names/descriptions** instead of raw A* internals,
  environmental-provenance badges, **on-route POI panel/markers** (parks,
  hospitals), detached directions selector/cards + step list, route preview via
  `RouteStepSimulator`, remove-route behavior, background env-quality badge.
- New services: `routeStepSimulator.js` (animated marker + active-step
  highlight), `services/poisAlongRoute.js` (real `/api/pois`, route-proximity
  computation, honest unavailable/available, **no synthetic POIs**),
  `utils/envQualityBadge.js` (decouples the loading overlay from slower env
  scoring, render tokens prevent stale badges).
- `static/js/algorithms/environmentalAStar.js`, `services/routePlanner.js`,
  `services/environmental.js`: frontend routing supports preference
  weights/POI proximity, real-environment seed tiles for A* selection cost,
  bounded/nonblocking `/api/environment` prefetch, concurrent post-route env
  sampling, explicit synthetic-fallback flags, opt-in legacy waypoints.
- `services/elevation.js`, `benchmark/benchmarkRunner.js`: Mapbox token
  externalized to `window.MAPBOX_ACCESS_TOKEN`.

### 4.4 Other user-facing templates

`homePage.html`, `404.html`, `not_authorized.html`, and `users/templates/*`
redesigned to `theme.css` / semantic responsive structures; `edit_profile.html`
exposes the default clinical condition as radio-card UI; `profile.html` adds a
responsive dashboard; `baseUser.html` preserves `next` via hidden input;
login/signup/preference forms get grouped action rows.

---

## 5. Config / Infra / Deploy — detail

*Verified by `codex-pp-diff`; cross-checked against file contents.*

- **`Dockerfile`** — `python:3.12-slim`; installs `build-essential`/`curl` +
  `requirements.txt`; creates `/app/{data,staticfiles,uploads}`; runs as
  non-root `pathplanner`; `ENTRYPOINT docker/entrypoint.sh`; default CMD runs
  Gunicorn on `0.0.0.0:8000` (3 workers, 120 s timeout).
- **`docker-compose.yml`** — `app` builds the repo, reads `.env` (overridable via
  `PATHPLANNER_ENV_FILE`), forces `DJANGO_DEBUG=0`, stores SQLite/static/uploads
  in named volumes, `/map/` healthcheck; `nginx:1.27-alpine` waits on app
  health, publishes `80:80`, mounts static/media read-only.
- **`docker/entrypoint.sh`** — hard-fails if `DJANGO_SECRET_KEY` or
  `DJANGO_ALLOWED_HOSTS` is missing, then `migrate --noinput` +
  `collectstatic --noinput` before exec.
- **`deploy/`** — Nginx configs (Docker upstream `app:8000` and host
  `127.0.0.1:8000`) and systemd units (Docker Compose oneshot, and non-Docker
  Gunicorn with `/etc/pathplanner/pathplanner.env`).
- **`.env.example`** — documents `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
  CSRF origins, SSL/cookie/HSTS flags, static/media/sqlite paths,
  `MAPBOX_ACCESS_TOKEN`, `OPENAQ_API_KEY`.
- **`.dockerignore` / `.gitignore`** — exclude git/worktrees/venvs/sqlite/
  backups/env/logs/test artifacts/uploads/staticfiles/node_modules; `.gitignore`
  keeps `.env.example` while ignoring all other `.env*`.
- **`requirements.txt`** — pinned (`asgiref==3.11.1`, `attrs==26.1.0`,
  `crispy-bootstrap4==2026.2`, `crispy-bootstrap5==2026.3`, `Django==5.2.15`,
  `django-crispy-forms==2.3`, `h11==0.16.0`) and adds **`gunicorn==23.0.0`**.

---

## 6. Notable security improvements

- **Hard-coded Mapbox token removed.** The original embedded a literal
  `pk.eyJ1...` Mapbox token in `static/js/services/elevation.js` (and used hard
  values elsewhere). The current code reads
  `globalThis.window?.MAPBOX_ACCESS_TOKEN || ''`; the token is injected
  server-side from `settings.MAPBOX_ACCESS_TOKEN` (env). Same for
  `benchmarkRunner.js` and the geocoder in `suggestions.js`.
- **Secrets out of source.** `SECRET_KEY` is no longer a literal in
  `settings.py`; it (and `DEBUG`, `ALLOWED_HOSTS`) come from the environment,
  with `ImproperlyConfigured` raised in production if unset.
- **Production transport hardening.** Optional SSL redirect, secure
  session/CSRF cookies, HSTS, and `SECURE_PROXY_SSL_HEADER` for proxied TLS.
- **`.gitignore` / `.dockerignore`** prevent committing/shipping `.env`, SQLite
  databases and backups.

---

## 7. Verification method

```sh
diff -rq \
  --exclude=.git --exclude=__pycache__ --exclude=node_modules \
  --exclude=.venv --exclude=.venv-codex --exclude=.worktrees \
  --exclude=staticfiles --exclude='*.sqlite3' --exclude=.env \
  "/Users/dtortoli/Downloads/pathplanner_browserbased_analysis (1)" \
  /Users/dtortoli/Code/pathplanner_browserbased_analysis
```

Each differing file was then inspected with a per-file unified diff
(`diff -u OLD NEW`); line counts in the inventory are `grep -c` of `>`/`<`
markers. Backend/A* entries were produced and verified by `claude-pp-diff`;
frontend and config/infra entries by `codex-pp-diff`; both runtimes
cross-checked the other's area against the same `diff -rq` output. No entry in
this document is inferred without a corresponding diff.
