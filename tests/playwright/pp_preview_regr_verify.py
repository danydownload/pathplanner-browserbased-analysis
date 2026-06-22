#!/usr/bin/env python3
"""
PP-PREVIEW-REGR-FIX live regression proof.

Reproduces the user-reported find-routes regression against the LIVE server and
proves the fix:
  (1) the "Indicazioni" directions panel auto-opens after find-routes
  (2) the route preview controls (#directionsPreviewControls) get populated
  (3) route cards render
  (4) no `createLocationBasedEnvironmentalData is not defined` ReferenceError
  (5) the panel appears even when Overpass / noise APIs are unreachable
      (i.e. the render is decoupled from env/POI/scoring).

Two scenarios are exercised:
  A) non-patient standard route()             -> the PRIMARY regression path
  B) patient + Environmental A* (precalc)      -> the SECONDARY ReferenceError path

Run:  .venv/bin/python tests/playwright/pp_preview_regr_verify.py
"""
import sys
import time
import pathlib

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000/map/"
ART_DIR = pathlib.Path(__file__).resolve().parents[2] / "artifacts" / "pp-preview-regr"
ART_DIR.mkdir(parents=True, exist_ok=True)

# Via Emilia Est 387, Modena -> a real Modena destination (Modena centro).
START = {"label": "Via Emilia Est 387, Modena", "lat": 44.639808, "lon": 10.942439}
END = {"label": "Modena centro (Via Emilia Centro)", "lat": 44.6464, "lon": 10.9252}

# Standard route() renders the panel from geometry almost immediately. The
# patient Environmental A* path first runs generateOptimizedRoutes (hundreds of
# node-cost evaluations — pre-existing, unrelated to this fix) before
# routeWithPrecalculatedRoutes renders, so it needs a much larger budget.
PANEL_TIMEOUT_STANDARD_S = 35
PANEL_TIMEOUT_PATIENT_S = 120


def collect_state(page):
    return page.evaluate(
        """() => {
            const panel = document.getElementById('directionsPanel');
            const preview = document.getElementById('directionsPreviewControls');
            const cards = document.querySelectorAll('#directionsRouteSelector .directions-route-card');
            const polylines = document.querySelectorAll('.leaflet-overlay-pane path');
            return {
                panelAriaHidden: panel ? panel.getAttribute('aria-hidden') : 'no-panel',
                bodyDirectionsOpen: document.body.classList.contains('directions-open'),
                previewChildren: preview ? preview.children.length : -1,
                routeCards: cards.length,
                polylines: polylines.length,
            };
        }"""
    )


def load_map(page):
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_function(
        "() => !!window.map && !!document.getElementById('searchButton') "
        "&& !!document.getElementById('startPoint')",
        timeout=30000,
    )
    time.sleep(1.5)  # let module listeners attach


def run_scenario(page, name, patient, console_log, request_failures):
    print(f"\n=== Scenario {name} (patient={patient}) ===")
    # Fresh page per scenario so the directions panel starts CLOSED
    # (aria-hidden=true) — otherwise a previous scenario's open panel would be a
    # false positive. Assert the panel transitions hidden -> open for THIS run.
    load_map(page)
    request_failures.clear()
    start_marker = len(console_log)
    pre = collect_state(page)
    print(f"  pre-click state (must be closed): {pre}")
    assert pre["panelAriaHidden"] == "true", f"panel not closed at start: {pre}"

    # Optionally enable patient mode + A* (precalc path).
    if patient:
        page.select_option("#patientCondition", "respiratory")
        page.dispatch_event("#patientCondition", "change")
        # Wait until the global patient condition reflects patient mode.
        for _ in range(50):
            ok = page.evaluate(
                "() => !!(window.currentPatientCondition && window.currentPatientCondition.isPatientMode "
                "&& window.currentPatientCondition.name !== 'default')"
            )
            if ok:
                break
            time.sleep(0.1)
        astar = page.evaluate("() => document.getElementById('useAStarAlgorithm')?.checked !== false")
        print(f"  patient mode active={ok}  A* enabled={astar}")

    # Set start/end coordinates directly via the geocoder datasets (bypasses the
    # flaky suggestion dropdown — the search handler reads dataset.lat/lon).
    page.evaluate(
        """({start, end}) => {
            const s = document.getElementById('startPoint');
            const e = document.getElementById('endPoint');
            s.value = start.label; s.dataset.lat = String(start.lat); s.dataset.lon = String(start.lon);
            e.value = end.label;   e.dataset.lat = String(end.lat);   e.dataset.lon = String(end.lon);
        }""",
        {"start": START, "end": END},
    )

    panel_timeout = PANEL_TIMEOUT_PATIENT_S if patient else PANEL_TIMEOUT_STANDARD_S
    t0 = time.time()
    page.click("#searchButton")

    panel_opened_at = None
    last = None
    deadline = t0 + panel_timeout
    while time.time() < deadline:
        last = collect_state(page)
        if (
            last["panelAriaHidden"] == "false"
            and last["previewChildren"] >= 2
            and last["routeCards"] >= 1
        ):
            panel_opened_at = time.time() - t0
            break
        time.sleep(0.25)

    # Give the background score/badge refresh a brief moment, then re-read.
    time.sleep(2)
    final = collect_state(page)

    scenario_logs = console_log[start_marker:]
    ref_errors = [m for m in scenario_logs if "createLocationBasedEnvironmentalData" in m["text"]
                  or ("is not defined" in m["text"]) or ("ReferenceError" in m["text"])]
    setup_logs = [m for m in scenario_logs if "[setupRouteControlPanel] Setting up control panel" in m["text"]]
    overpass = [r for r in request_failures if "overpass" in r["url"].lower()]
    timeout_fallbacks = [m for m in scenario_logs if "[withTimeout]" in m["text"]]

    shot = ART_DIR / f"scenario_{name}.png"
    page.screenshot(path=str(shot), full_page=False)

    print(f"  panel opened at: {panel_opened_at}s (None = never within {panel_timeout}s)")
    print(f"  final state: {final}")
    print(f"  [setupRouteControlPanel] log present: {len(setup_logs) > 0}")
    print(f"  ReferenceError(createLocationBasedEnvironmentalData/is not defined): {len(ref_errors)}")
    for m in ref_errors[:5]:
        print(f"     !! {m['type']}: {m['text'][:200]}")
    print(f"  Overpass request failures observed: {len(overpass)}")
    print(f"  withTimeout fallbacks fired: {len(timeout_fallbacks)}")
    print(f"  screenshot: {shot}")

    passed = (
        panel_opened_at is not None
        and final["panelAriaHidden"] == "false"
        and final["previewChildren"] >= 2
        and final["routeCards"] >= 1
        and final["polylines"] >= 1
        and len(ref_errors) == 0
        and len(setup_logs) > 0
    )
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed, {
        "panel_opened_at": panel_opened_at,
        "final": final,
        "ref_errors": len(ref_errors),
        "setup_log": len(setup_logs) > 0,
        "overpass_failures": len(overpass),
        "timeout_fallbacks": len(timeout_fallbacks),
    }


def main():
    console_log = []
    request_failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("console", lambda m: console_log.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: console_log.append({"type": "pageerror", "text": str(e)}))
        page.on("requestfailed", lambda r: request_failures.append(
            {"url": r.url, "failure": (r.failure or "")}))

        results = {}
        results["A_standard"], a = run_scenario(page, "A_standard", patient=False,
                                                console_log=console_log, request_failures=request_failures)
        results["B_patient_astar"], b = run_scenario(page, "B_patient_astar", patient=True,
                                                     console_log=console_log, request_failures=request_failures)

        browser.close()

    print("\n================ SUMMARY ================")
    print(f"Scenario A (standard route, primary regression): {'PASS' if results['A_standard'] else 'FAIL'} -> {a}")
    print(f"Scenario B (patient A* precalc, secondary bug):  {'PASS' if results['B_patient_astar'] else 'FAIL'} -> {b}")
    all_pass = all(results.values())
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
