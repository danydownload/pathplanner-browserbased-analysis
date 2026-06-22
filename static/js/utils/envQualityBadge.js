// PP-LOAD-PERF: non-blocking environmental-quality badge (anti-stale guarded).
//
// The loading overlay is closed as soon as the route polyline is on the map;
// environmental quality keeps computing in the background and resolves into a
// small fixed badge. A monotonically-increasing render token (one per route
// run) guards against rapid route switches showing a stale result.
//
// Kept dependency-light (only LoadingScreen + DOM) so the anti-stale / overlay
// decoupling logic is unit-testable in isolation.
import * as LoadingScreen from './loadingScreen.js';

let _envQualityRenderToken = 0;
let _overlayClosedForRun = false;
// True while a route run is in flight (badge legitimately on screen). Lets the
// route-clear cleanup distinguish an active spinner from an orphaned badge.
let _runActive = false;
// Wall-clock start of the current run — used to log the DoD measurement live:
// (a) overlay-close at first-polyline, (b) full env completion, relative to the
// route request. Printed to the console during any real route so the timing is
// captured from the real flow, not estimated.
let _runStartedAt = 0;

function _now() {
    return (typeof performance !== 'undefined' && performance.now)
        ? performance.now()
        : Date.now();
}

// Test/inspection helper — current run token.
export function getEnvQualityRenderToken() {
    return _envQualityRenderToken;
}

// Begin a new route run: bump the token, reset the per-run overlay-close latch,
// and show the in-progress badge. Returns the token to thread through the run.
export function beginEnvQualityRun() {
    _envQualityRenderToken += 1;
    const token = _envQualityRenderToken;
    _overlayClosedForRun = false;
    _runActive = true;
    _runStartedAt = _now();
    showEnvQualityBadge(token);
    return token;
}

// Remove the badge node outright. Called on explicit route-clear so a fixed
// (document.body) badge can never linger/orphan once routes drop to 0. No-op
// while a run is active (the badge belongs to the in-flight run).
export function clearEnvQualityBadge(force = false) {
    if (_runActive && !force) {
        return;
    }
    const doc = globalThis.document;
    const badge = doc?.getElementById('envQualityBadge');
    if (badge) {
        if (badge._hideTimer) {
            clearTimeout(badge._hideTimer);
            badge._hideTimer = null;
        }
        if (badge.parentNode) {
            badge.parentNode.removeChild(badge);
        }
    }
}

// Idempotent: close the full-screen loading overlay the first time a route's
// polyline is actually rendered (control has a line/route layer). Subsequent
// calls within the same run are no-ops.
export function closeOverlayAtFirstPolyline(routingControl) {
    if (_overlayClosedForRun) {
        return;
    }
    const doc = globalThis.document;
    if (!doc) {
        return;
    }
    const lineReady = !routingControl
        || routingControl._line
        || routingControl._selectedRoute
        || (routingControl._routes && routingControl._routes.length > 0);
    const finishClose = () => {
        if (_overlayClosedForRun) {
            return;
        }
        _overlayClosedForRun = true;
        try {
            LoadingScreen.hide(doc);
            const dt = _runStartedAt ? (_now() - _runStartedAt) : 0;
            console.log(`[PP-LOAD-PERF] overlay closed at first-polyline +${dt.toFixed(0)}ms after route request`);
        } catch (e) {
            console.warn('[envQualityBadge] overlay hide failed:', e);
        }
    };
    if (lineReady) {
        finishClose();
    } else {
        // Leaflet has the route but the layer may render on the next frame.
        setTimeout(finishClose, 0);
    }
}

function getEnvQualityBadgeHost() {
    return globalThis.document?.body || null;
}

export function showEnvQualityBadge(token, message = 'Calcolo qualità ambientale…') {
    if (token !== _envQualityRenderToken) {
        return; // stale run
    }
    const doc = globalThis.document;
    if (!doc) {
        return;
    }
    let badge = doc.getElementById('envQualityBadge');
    if (!badge) {
        badge = doc.createElement('div');
        badge.id = 'envQualityBadge';
        badge.setAttribute('role', 'status');
        badge.setAttribute('aria-live', 'polite');
        badge.style.cssText = [
            'position:fixed',
            'bottom:20px',
            'left:20px',
            'z-index:9000',
            'display:flex',
            'align-items:center',
            'gap:8px',
            'max-width:320px',
            'padding:8px 12px',
            'border-radius:10px',
            'font-size:13px',
            'font-weight:500',
            'line-height:1.3',
            'color:#fff',
            'background:rgba(20,20,28,0.92)',
            'box-shadow:0 4px 16px rgba(0,0,0,0.35)',
            'backdrop-filter:blur(6px)',
            '-webkit-backdrop-filter:blur(6px)',
            'transition:opacity 0.25s ease-in-out',
            'opacity:0'
        ].join(';');
        const host = getEnvQualityBadgeHost();
        if (!host) {
            return;
        }
        host.appendChild(badge);
        // Inject the spinner keyframes once (reused by the loading overlay name).
        if (!doc.getElementById('loadingSpinnerStyles')) {
            const style = doc.createElement('style');
            style.id = 'loadingSpinnerStyles';
            style.textContent = '@keyframes spin{0%{transform:rotate(0)}100%{transform:rotate(360deg)}}';
            doc.head.appendChild(style);
        }
        if (typeof requestAnimationFrame === 'function') {
            requestAnimationFrame(() => { badge.style.opacity = '1'; });
        } else {
            badge.style.opacity = '1';
        }
    }
    if (badge._hideTimer) {
        clearTimeout(badge._hideTimer);
        badge._hideTimer = null;
    }
    badge.dataset.token = String(token);
    badge.style.opacity = '1';
    badge.innerHTML =
        '<span style="width:14px;height:14px;border:2px solid rgba(255,255,255,0.35);'
        + 'border-top-color:#fff;border-radius:50%;display:inline-block;'
        + 'animation:spin 0.8s linear infinite;flex:0 0 auto"></span>'
        + '<span class="env-quality-text"></span>';
    const textNode = badge.querySelector('.env-quality-text');
    if (textNode) {
        textNode.textContent = message;
    }
}

// Resolve the badge in place. `status` is one of 'real' | 'unavailable' | 'estimate'.
export function resolveEnvQualityBadge(token, status, text) {
    if (token !== _envQualityRenderToken) {
        return; // a newer route run superseded this one — do not bleed
    }
    const doc = globalThis.document;
    if (!doc) {
        return;
    }
    const badge = doc.getElementById('envQualityBadge');
    if (!badge || badge.dataset.token !== String(token)) {
        return;
    }
    _runActive = false; // run finished — badge may now be cleared on route-clear
    const dt = _runStartedAt ? (_now() - _runStartedAt) : 0;
    console.log(`[PP-LOAD-PERF] env quality '${status}' resolved +${dt.toFixed(0)}ms after route request (overlay already closed) -> ${text}`);
    const dot = status === 'real' ? '#34c759'
        : status === 'estimate' ? '#ffd60a'
        : '#ff9f0a';
    badge.innerHTML =
        '<span style="width:9px;height:9px;border-radius:50%;display:inline-block;'
        + 'flex:0 0 auto;background:' + dot + '"></span>'
        + '<span class="env-quality-text"></span>';
    const textNode = badge.querySelector('.env-quality-text');
    if (textNode) {
        textNode.textContent = text;
    }
    // Auto-dismiss after a few seconds so it does not linger.
    badge._hideTimer = setTimeout(() => {
        if (badge.dataset.token !== String(token)) {
            return;
        }
        badge.style.opacity = '0';
        setTimeout(() => {
            if (badge.parentNode && badge.dataset.token === String(token)) {
                badge.parentNode.removeChild(badge);
            }
        }, 300);
    }, 6000);
}

// Build the honest badge text/status from a route's environmental quality.
// Only presents a numeric quality when REAL data is actually present
// (realDataPercentage > 0); otherwise it is explicitly labelled estimate /
// unavailable — never a synthetic value dressed up as a real measurement.
export function envQualityBadgeFromRoute(route) {
    const realPct = Number(
        route?.realDataPercentage ?? route?.envStats?.realDataPercentage ?? 0
    );
    const score = Number(route?.environmentScore);
    const hasScore = Number.isFinite(score);
    if (realPct > 0 && hasScore) {
        return {
            status: 'real',
            text: `Qualità ambientale: ${score.toFixed(1)}/10 (${realPct.toFixed(0)}% dati reali)`
        };
    }
    if (hasScore) {
        return {
            status: 'estimate',
            text: 'Qualità ambientale: stima (dati reali non disponibili)'
        };
    }
    return {
        status: 'unavailable',
        text: 'Qualità ambientale non disponibile'
    };
}
