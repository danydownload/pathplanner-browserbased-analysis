// PP-LOAD-PERF proof harness (run: `node tests/perf/envQualityBadge.proof.mjs`).
//
// Exercises the REAL shipped functions in static/js/utils/envQualityBadge.js +
// static/js/utils/loadingScreen.js against a minimal DOM stub to prove:
//   1. The loading overlay closes at first-polyline, DECOUPLED from (and well
//      before) environmental completion.
//   2. The per-run renderToken anti-stale guard prevents cross-route badge bleed.
//   3. The badge labels quality honestly (real vs estimate vs unavailable),
//      never presenting synthetic data as a real measurement.
//
// Timings printed are REAL wall-clock measurements of the control flow, with a
// deliberately injected env delay standing in for the (network-bound) env layer.

// ---------------------------------------------------------------------------
// Minimal DOM stub — just enough for loadingScreen.js + envQualityBadge.js.
// ---------------------------------------------------------------------------
const registry = new Map();

function makeEl(tag) {
    const el = {
        tagName: tag,
        _id: '',
        style: { cssText: '', _props: {} },
        dataset: {},
        attrs: {},
        children: [],
        parentNode: null,
        _innerHTML: '',
        _text: '',
        _envTextChild: null,
        isConnected: false,
        get id() { return this._id; },
        set id(v) { this._id = v; if (v) registry.set(v, el); },
        setAttribute(k, v) { this.attrs[k] = v; },
        getAttribute(k) { return this.attrs[k]; },
        appendChild(child) { child.parentNode = el; child.isConnected = true; this.children.push(child); return child; },
        removeChild(child) {
            const i = this.children.indexOf(child);
            if (i >= 0) this.children.splice(i, 1);
            child.parentNode = null; child.isConnected = false;
            return child;
        },
        remove() { if (this.parentNode) this.parentNode.removeChild(this); },
        get innerHTML() { return this._innerHTML; },
        set innerHTML(html) {
            this._innerHTML = html;
            // The badge sets innerHTML containing a <span class="env-quality-text">.
            // Model just that child so querySelector('.env-quality-text') resolves.
            if (html.includes('env-quality-text')) {
                this._envTextChild = makeEl('span');
                this._envTextChild.attrs.class = 'env-quality-text';
            } else {
                this._envTextChild = null;
            }
        },
        get textContent() { return this._text; },
        set textContent(v) { this._text = v; },
        querySelector(sel) {
            if (sel === '.env-quality-text') return this._envTextChild;
            return null;
        }
    };
    return el;
}

const documentStub = {
    body: makeEl('body'),
    head: makeEl('head'),
    createElement: (tag) => makeEl(tag),
    // Mirror real DOM: only return elements still attached to the tree.
    getElementById: (id) => {
        const el = registry.get(id);
        return el && el.parentNode ? el : null;
    }
};

globalThis.document = documentStub;

// ---------------------------------------------------------------------------
const badge = await import('../../static/js/utils/envQualityBadge.js');
const LoadingScreen = await import('../../static/js/utils/loadingScreen.js');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓ ${msg}`); }
    else { console.log(`  ✗ ${msg}`); failures++; }
}
const badgeText = () => document.getElementById('envQualityBadge')?.querySelector('.env-quality-text')?.textContent;
const overlayEl = () => document.getElementById('loadingOverlay');
// Visible = present in the DOM AND not faded out. hide() starts a fade-out
// (opacity -> '0') immediately, then removes the node ~300ms later.
const overlayVisible = () => {
    const el = overlayEl();
    return el !== null && el.parentNode !== null && el.style.opacity !== '0';
};
const overlayRemoved = () => overlayEl() === null || overlayEl().parentNode === null;

// ===========================================================================
console.log('\n[TEST 1] Overlay closes at first-polyline, decoupled from env completion');
{
    const ENV_DELAY_MS = 1500; // stands in for the network-bound env layer
    const t0 = performance.now();

    await LoadingScreen.show(document); // user clicks search -> overlay up
    await sleep(20); // let the 10ms fade-in settle (opacity 0 -> 1)
    assert(overlayVisible(), 'overlay shown on route request');

    const runToken = badge.beginEnvQualityRun();
    assert(badgeText() === 'Calcolo qualità ambientale…', 'in-progress badge shown');

    // handleOnRouteFound ordering: polyline drawn -> close overlay BEFORE env.
    badge.closeOverlayAtFirstPolyline({ _line: {} });
    const tClose = performance.now() - t0;
    assert(!overlayVisible(), 'overlay close INITIATED at first-polyline (fade-out)');

    // env keeps computing in the background...
    await sleep(ENV_DELAY_MS);
    assert(overlayRemoved(), 'overlay fully removed long before env completion');
    badge.resolveEnvQualityBadge(runToken, 'real', 'Qualità ambientale: 7.2/10 (60% dati reali)');
    const tDone = performance.now() - t0;

    console.log(`    overlay-close @ ${tClose.toFixed(1)}ms | full-env-completion @ ${tDone.toFixed(1)}ms`);
    console.log(`    overlay no longer blocks for the env duration (gap ~${(tDone - tClose).toFixed(0)}ms)`);
    assert(tClose < 50, `overlay closed near-instantly (<50ms), not after env (${tClose.toFixed(1)}ms)`);
    assert(tDone - tClose > ENV_DELAY_MS * 0.8, 'env completed well AFTER overlay close (decoupled)');
    assert(badgeText().includes('7.2/10'), 'badge resolved to real quality in place');
}

// ===========================================================================
console.log('\n[TEST 2] Anti-stale guard: rapid route switch shows no stale badge');
{
    const tokenA = badge.beginEnvQualityRun();
    const tokenB = badge.beginEnvQualityRun(); // user switches route before A resolved
    assert(tokenB > tokenA, 'each run gets a fresh monotonically-increasing token');

    // Route A's env resolves LATE (after the switch) — must be ignored.
    badge.resolveEnvQualityBadge(tokenA, 'real', 'STALE-A 9.9/10');
    assert(badgeText() !== 'STALE-A 9.9/10', 'stale route A result REJECTED (no cross-route bleed)');
    assert(badgeText() === 'Calcolo qualità ambientale…', 'badge still shows current run B in-progress');

    // Route B (current) resolves — must update.
    badge.resolveEnvQualityBadge(tokenB, 'real', 'FRESH-B 6.1/10');
    assert(badgeText() === 'FRESH-B 6.1/10', 'current route B result applied');
}

// ===========================================================================
console.log('\n[TEST 3] Honest labeling (never synthetic-as-real)');
{
    const real = badge.envQualityBadgeFromRoute({ environmentScore: 7.2, realDataPercentage: 60 });
    assert(real.status === 'real' && real.text.includes('7.2/10') && real.text.includes('60% dati reali'),
        `real data -> "${real.text}"`);

    const estimate = badge.envQualityBadgeFromRoute({ environmentScore: 5.0, realDataPercentage: 0 });
    assert(estimate.status === 'estimate' && /stima/i.test(estimate.text) && !/\/10/.test(estimate.text),
        `synthetic (0% real) -> labelled estimate, NO numeric score: "${estimate.text}"`);

    const unavailable = badge.envQualityBadgeFromRoute({ realDataPercentage: 0 });
    assert(unavailable.status === 'unavailable' && /non disponibile/i.test(unavailable.text),
        `no score -> "${unavailable.text}"`);
}

// ===========================================================================
console.log('\n[TEST 4] Fixed-body badge orphan cleanup on route-clear');
{
    const token = badge.beginEnvQualityRun();
    assert(document.getElementById('envQualityBadge') !== null, 'badge present during active run');

    // Route-clear WHILE a run is active (env still computing) must NOT remove it.
    badge.clearEnvQualityBadge();
    assert(document.getElementById('envQualityBadge') !== null, 'badge kept while run active (no-op)');

    // Run finishes...
    badge.resolveEnvQualityBadge(token, 'estimate', 'Qualità ambientale: stima (dati reali non disponibili)');
    // ...then an explicit route-clear must remove the fixed badge (no orphan).
    badge.clearEnvQualityBadge();
    assert(document.getElementById('envQualityBadge') === null, 'badge REMOVED on route-clear after run (no orphan)');
}

console.log(`\n${failures === 0 ? 'ALL PROOFS PASSED' : failures + ' PROOF(S) FAILED'}`);
process.exit(failures === 0 ? 0 : 1);
