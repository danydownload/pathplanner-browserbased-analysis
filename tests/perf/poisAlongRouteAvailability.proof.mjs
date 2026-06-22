// PP-FB-2 proof harness (run: `node tests/perf/poisAlongRouteAvailability.proof.mjs`).
//
// Proves the route POI service distinguishes:
//   1. real data available with nearby POIs,
//   2. real data unavailable (backend/Overpass failure),
//   3. a later successful retry after failure (failure is not cached as empty).

import assert from 'node:assert/strict';

const service = await import('../../static/js/services/poisAlongRoute.js');

const route = [
    { lat: 44.6500, lng: 10.9200 },
    { lat: 44.6500, lng: 10.9300 },
];

let calls = 0;
globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) {
        return {
            ok: false,
            status: 500,
            json: async () => ({ error: 'pois lookup failed' }),
        };
    }
    return {
        ok: true,
        json: async () => ({
            pois: [
                { name: 'Ospedale test', lat: 44.65005, lon: 10.925, kind: 'hospital' },
                { name: 'Troppo lontano', lat: 44.6600, lon: 10.925, kind: 'hospital' },
            ],
            count: 2,
            source: 'OpenStreetMap-Overpass',
        }),
    };
};

const unavailable = await service.getPoisAlongRouteResult('hospitals', route);
assert.equal(unavailable.status, 'unavailable');
assert.deepEqual(unavailable.items, []);
assert.match(unavailable.error, /500|pois lookup failed/i);

const retry = await service.getPoisAlongRouteResult('hospitals', route);
assert.equal(retry.status, 'available');
assert.equal(retry.items.length, 1);
assert.equal(retry.items[0].name, 'Ospedale test');
assert.equal(calls, 2, 'failed POI fetch must not be cached as a real empty result');

const legacy = await service.getPoisAlongRoute('hospitals', route);
assert.equal(legacy.length, 1);
assert.equal(calls, 2, 'successful POI fetch should be cached for legacy callers');

console.log('[poisAlongRouteAvailability] PASS');
