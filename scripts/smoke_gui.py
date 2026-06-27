#!/usr/bin/env python
"""Smoke-test the PathPlanner map UI against a running server.

This is a runtime GUI check, not a hermetic unit test. It opens the real map
page, uses fixed Modena coordinates, verifies route rendering and layout on
desktop/mobile viewports, and saves screenshots for visual review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENSHOT_DIR = ROOT / 'artifacts' / 'gui-smoke-current'

START = {
    'label': 'Via Emilia Est 387, Modena',
    'lat': 44.6398102,
    'lon': 10.9424172,
}
END = {
    'label': 'Centro Commerciale I Portali, Modena',
    'lat': 44.6444776,
    'lon': 10.9569078,
}


def _set_route_inputs(page) -> None:
    page.evaluate(
        """({start, end}) => {
            const startInput = document.getElementById('startPoint');
            const endInput = document.getElementById('endPoint');
            startInput.value = start.label;
            startInput.dataset.lat = String(start.lat);
            startInput.dataset.lon = String(start.lon);
            endInput.value = end.label;
            endInput.dataset.lat = String(end.lat);
            endInput.dataset.lon = String(end.lon);
            for (const input of [startInput, endInput]) {
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }

            const mode = document.getElementById('transportMode');
            if (mode) {
                mode.value = 'walking';
                mode.dispatchEvent(new Event('change', { bubbles: true }));
            }

            const condition = document.getElementById('patientCondition');
            if (condition) {
                condition.value = 'respiratory';
                condition.dispatchEvent(new Event('change', { bubbles: true }));
            }

            const astar = document.getElementById('useAStarAlgorithm');
            if (astar && !astar.checked) {
                astar.click();
            }
        }""",
        {'start': START, 'end': END},
    )


def _collect_metrics(page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const visible = (element) => {
                if (!element) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const panel = document.getElementById('directionsPanel');
            const selector = document.getElementById('directionsRouteSelector') || document.querySelector('.route-selector');
            const summary = document.getElementById('directionsSummary');
            const steps = [...document.querySelectorAll('.directions-step, .turn-directions-step')].filter(visible);
            const cards = [...document.querySelectorAll('.directions-route-card, .route-item')].filter(visible);
            const layerText = [...document.querySelectorAll('button, .layer-chip')]
                .map((element) => element.textContent.trim())
                .join(' ');
            const explanationText = [...document.querySelectorAll('.route-card-explanation, .route-card-sources, .directions-route-card')]
                .map((element) => element.textContent.trim())
                .join(' ');
            return {
                panelOpen: panel?.getAttribute('aria-hidden') === 'false',
                bodyDirectionsOpen: document.body.classList.contains('directions-open'),
                cards: cards.length,
                steps: steps.length,
                polylines: document.querySelectorAll('.leaflet-overlay-pane path').length,
                hasSummary: !!summary && visible(summary),
                summaryMarginBottom: summary ? parseFloat(getComputedStyle(summary).marginBottom) : null,
                hasLayerButtons: /PM2\\.5/.test(layerText) && /PM10/.test(layerText) && /NO/.test(layerText),
                hasExplanation: /air quality|slope|GraphHopper|SQLite|Open-Meteo|AQ|pendenza|qualit/i.test(explanationText),
                pageScrollWidth: document.documentElement.scrollWidth,
                viewportWidth: window.innerWidth,
                routeSelectorText: selector ? selector.textContent.replace(/\\s+/g, ' ').trim().slice(0, 500) : '',
            };
        }"""
    )


def _collect_layer_metrics(page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const visible = (element) => {
                if (!element) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const canvases = [...document.querySelectorAll('.leaflet-overlay-pane canvas')].filter(visible);
            const markerIcons = [...document.querySelectorAll('.leaflet-marker-pane .leaflet-marker-icon, .leaflet-marker-pane .marker-cluster')].filter(visible);
            const layerStatus = document.getElementById('layerStatus');
            const layerLegend = document.getElementById('layerLegend');
            return {
                heatCanvases: canvases.length,
                markerIcons: markerIcons.length,
                statusText: layerStatus ? layerStatus.textContent.replace(/\\s+/g, ' ').trim() : '',
                legendVisible: !!layerLegend && visible(layerLegend),
                legendText: layerLegend ? layerLegend.textContent.replace(/\\s+/g, ' ').trim() : '',
            };
        }"""
    )


def _run_viewport(page, *, base_url: str, screenshot_dir: Path, name: str, width: int, height: int) -> dict[str, Any]:
    console_errors: list[str] = []
    request_failures: list[dict[str, Any]] = []
    page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)
    page.on('pageerror', lambda error: console_errors.append(str(error)))
    page.on('requestfailed', lambda request: request_failures.append({'url': request.url, 'failure': request.failure}))

    page.set_viewport_size({'width': width, 'height': height})
    page.goto(f'{base_url.rstrip("/")}/map/', wait_until='domcontentloaded')
    page.wait_for_function(
        "() => !!window.map && !!document.getElementById('searchButton') && !!document.getElementById('pm25')",
        timeout=30000,
    )

    # Layers must be usable before a route/directions overlay is open.
    page.click('#pm25', timeout=10000)
    page.wait_for_function(
        """() => {
            const pressed = document.getElementById('pm25')?.getAttribute('aria-pressed') === 'true';
            const canvas = document.querySelectorAll('.leaflet-overlay-pane canvas').length > 0;
            const status = document.getElementById('layerStatus')?.textContent || '';
            return pressed && (canvas || /no .*readings|unavailable|could not/i.test(status));
        }""",
        timeout=30000,
    )
    layer_pressed_before_route = page.locator('#pm25').get_attribute('aria-pressed') == 'true'
    layer_metrics_before_route = _collect_layer_metrics(page)

    _set_route_inputs(page)
    page.click('#searchButton')
    page.wait_for_function(
        """() => {
            const panel = document.getElementById('directionsPanel');
            const cards = document.querySelectorAll('.directions-route-card, .route-item');
            const steps = document.querySelectorAll('.directions-step, .turn-directions-step');
            return panel
                && panel.getAttribute('aria-hidden') === 'false'
                && cards.length >= 1
                && steps.length >= 1;
        }""",
        timeout=120000,
    )
    page.wait_for_timeout(600)
    route_metrics = _collect_metrics(page)
    route_screenshot_path = screenshot_dir / f'{name}-route.png'
    page.screenshot(path=str(route_screenshot_path), full_page=False)

    # On mobile the directions panel intentionally overlays the map/sidebar.
    # Closing it must restore access to layer controls.
    page.click('#directionsClose', timeout=10000)
    page.wait_for_function(
        "() => document.getElementById('directionsPanel')?.getAttribute('aria-hidden') === 'true'",
        timeout=10000,
    )
    page.click('#pm25', timeout=10000)
    page.wait_for_timeout(250)
    layer_pressed_after_close = page.locator('#pm25').get_attribute('aria-pressed') == 'false'

    closed_screenshot_path = screenshot_dir / f'{name}-closed.png'
    page.screenshot(path=str(closed_screenshot_path), full_page=False)

    bad_console = [
        error for error in console_errors
        if 'favicon' not in error.lower()
        and 'user denied geolocation' not in error.lower()
    ]
    bad_requests = [
        failure for failure in request_failures
        if '/api/' in failure['url']
    ]
    errors: list[str] = []
    if not layer_pressed_before_route:
        errors.append('PM2.5 layer did not toggle before route')
    if layer_metrics_before_route['heatCanvases'] < 1:
        errors.append('PM2.5 layer did not render a heatmap canvas')
    if not layer_pressed_after_close:
        errors.append('PM2.5 layer did not toggle after closing directions')
    if not route_metrics['panelOpen']:
        errors.append('directions panel did not open')
    if route_metrics['cards'] < 1:
        errors.append('no route cards')
    if route_metrics['steps'] < 1:
        errors.append('no direction steps')
    if route_metrics['polylines'] < 1:
        errors.append('no route polylines')
    if not route_metrics['hasSummary']:
        errors.append('distance/duration summary missing')
    if route_metrics['summaryMarginBottom'] is not None and route_metrics['summaryMarginBottom'] < 18:
        errors.append('distance/duration summary vertical spacing too small')
    if not route_metrics['hasLayerButtons']:
        errors.append('layer buttons missing')
    if not route_metrics['hasExplanation']:
        errors.append('route explanation/source text missing')
    if route_metrics['pageScrollWidth'] > route_metrics['viewportWidth'] + 2:
        errors.append('horizontal overflow')
    if bad_console:
        errors.append('console errors: ' + '; '.join(bad_console[-3:]))
    if bad_requests:
        errors.append('api request failures: ' + json.dumps(bad_requests[-3:]))

    return {
        'name': name,
        'viewport': {'width': width, 'height': height},
        'status': 'failed' if errors else 'passed',
        'errors': errors,
        'metrics': route_metrics,
        'layer_metrics_before_route': layer_metrics_before_route,
        'route_screenshot': str(route_screenshot_path),
        'closed_screenshot': str(closed_screenshot_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--screenshot-dir', type=Path, default=DEFAULT_SCREENSHOT_DIR)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    args.screenshot_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        results = []
        for name, width, height in (
            ('desktop', 1440, 1000),
            ('mobile', 390, 844),
        ):
            page = browser.new_page()
            try:
                results.append(
                    _run_viewport(
                        page,
                        base_url=args.base_url,
                        screenshot_dir=args.screenshot_dir,
                        name=name,
                        width=width,
                        height=height,
                    )
                )
            finally:
                page.close()
        browser.close()

    failed = [result for result in results if result['errors']]
    summary = {
        'base_url': args.base_url,
        'passed': len(results) - len(failed),
        'failed': len(failed),
        'results': results,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        for result in results:
            if result['status'] == 'passed':
                print(
                    f"PASS {result['name']}: {result['metrics']['cards']} cards, "
                    f"{result['metrics']['steps']} steps, screenshot={result['route_screenshot']}"
                )
            else:
                print(f"FAIL {result['name']}: {'; '.join(result['errors'])}")
        print(f"Summary: {summary['passed']} passed, {summary['failed']} failed")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
