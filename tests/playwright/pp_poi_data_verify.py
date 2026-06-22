#!/usr/bin/env python3
"""
PP-FB-2 live proof.

Loads the real :8000 map, but routes the changed JS files and /api/pois calls to
this worktree so the proof exercises the patched POI data path without taking the
shared :8000 server down.

Run:
  .venv/bin/python tests/playwright/pp_poi_data_verify.py
"""

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8000/map/"
PATCHED_API_BASE = "http://127.0.0.1:8001"
ART_DIR = ROOT / "artifacts" / "pp-poi-data"
ART_DIR.mkdir(parents=True, exist_ok=True)

START = {"label": "Ospedale Estense, Modena", "lat": 44.6473062, "lon": 10.9207252}
END = {"label": "Policlinico di Modena", "lat": 44.6354633, "lon": 10.9426728}


def fulfill_static(route, relative_path):
    body = (ROOT / relative_path).read_text()
    route.fulfill(
        status=200,
        content_type="application/javascript; charset=utf-8",
        body=body,
    )


def fulfill_patched_api(route):
    request = route.request
    path_and_query = request.url.split("/api/pois", 1)[1]
    target = f"{PATCHED_API_BASE}/api/pois{path_and_query}"
    try:
        with urllib.request.urlopen(target, timeout=90) as response:
            route.fulfill(
                status=response.status,
                content_type=response.headers.get("content-type", "application/json"),
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        route.fulfill(
            status=exc.code,
            content_type="application/json",
            body=exc.read() or json.dumps({"error": str(exc)}),
        )


def collect_on_route_state(page):
    return page.evaluate(
        """() => {
            const sections = [...document.querySelectorAll('#onRouteContent .on-route-category')].map(section => ({
                title: section.querySelector('.on-route-category-title')?.textContent?.trim() || '',
                text: section.textContent.replace(/\\s+/g, ' ').trim(),
                itemCount: section.querySelectorAll('.on-route-item').length,
                loading: !!section.querySelector('.on-route-loading'),
                unavailable: section.textContent.includes('Dati reali')
            }));
            return {
                panelOpen: document.getElementById('directionsPanel')?.getAttribute('aria-hidden') === 'false',
                routeCards: document.querySelectorAll('#directionsRouteSelector .directions-route-card').length,
                polylines: document.querySelectorAll('.leaflet-overlay-pane path').length,
                onRouteText: document.getElementById('onRouteContent')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
                sections,
            };
        }"""
    )


def main():
    console_log = []
    request_failures = []
    api_proxy_hits = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("console", lambda m: console_log.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: console_log.append({"type": "pageerror", "text": str(e)}))
        page.on("requestfailed", lambda r: request_failures.append({"url": r.url, "failure": r.failure}))

        page.route("**/static/js/master/routes.js", lambda route: fulfill_static(route, "static/js/master/routes.js"))
        page.route(
            "**/static/js/services/poisAlongRoute.js",
            lambda route: fulfill_static(route, "static/js/services/poisAlongRoute.js"),
        )
        page.route(
            "**/api/pois?**",
            lambda route: (api_proxy_hits.append(route.request.url), fulfill_patched_api(route)),
        )

        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "() => !!window.map && !!document.getElementById('searchButton') && !!document.getElementById('startPoint')",
            timeout=30000,
        )
        time.sleep(1.5)

        page.evaluate(
            """({start, end}) => {
                const s = document.getElementById('startPoint');
                const e = document.getElementById('endPoint');
                s.value = start.label; s.dataset.lat = String(start.lat); s.dataset.lon = String(start.lon);
                e.value = end.label; e.dataset.lat = String(end.lat); e.dataset.lon = String(end.lon);
                const mode = document.getElementById('transportMode');
                if (mode) mode.value = 'walking';
            }""",
            {"start": START, "end": END},
        )

        page.click("#searchButton")
        deadline = time.time() + 45
        state = None
        while time.time() < deadline:
            state = collect_on_route_state(page)
            if state["panelOpen"] and state["routeCards"] >= 1 and state["polylines"] >= 1:
                break
            time.sleep(0.25)
        assert state and state["panelOpen"], f"directions panel did not open: {state}"

        # On-route POIs now render inline below the steps (no separate tab),
        # so there is no tab to click — just wait for the sections to load.
        deadline = time.time() + 120
        while time.time() < deadline:
            state = collect_on_route_state(page)
            if state["sections"] and not any(section["loading"] for section in state["sections"]):
                break
            time.sleep(0.5)

        shot = ART_DIR / "pp_poi_data_verify.png"
        page.screenshot(path=str(shot), full_page=False)
        browser.close()

    assert len(api_proxy_hits) >= 2, f"expected parks+hospitals /api/pois calls, got {len(api_proxy_hits)}"
    assert state and state["sections"], f"on-route sections missing: {state}"
    assert not any(section["unavailable"] for section in state["sections"]), state
    assert not any("Nessun ospedale" in section["text"] for section in state["sections"]), state
    assert not any("Nessun parco" in section["text"] for section in state["sections"]), state
    assert any(section["itemCount"] > 0 for section in state["sections"]), state
    assert not any("ReferenceError" in item["text"] for item in console_log), console_log[-20:]

    print("[pp-poi-data] PASS")
    print(f"  api_proxy_hits={len(api_proxy_hits)}")
    print(f"  sections={state['sections']}")
    print(f"  request_failures={len(request_failures)}")
    print(f"  screenshot={shot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
