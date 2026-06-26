"""Focused regression tests for PP-FIX-ALGO (TODO5-algo + P0 audit fixes).

Proves the three guarantees added to ``environmental_astar`` (kept consistent with
the JS twin ``static/js/algorithms/environmentalAStar.js``):

  1. Arc costs are ALWAYS >= the physical (haversine) distance and never negative
     — the green/POI rewards can no longer drive an edge below its distance, so the
     straight-line heuristic stays admissible/consistent (P0: no negative weights).
  2. The reconstructed path begins EXACTLY at A (start) and ends EXACTLY at B (goal)
     — the search runs on a free grid whose nodes never coincide with A/B and goal
     is "reached" within 50 m of B (TODO5-algo).
  3. The decrease-key is correct: a node whose g-score improves while it is already
     on the open heap is re-prioritized (lazy-deletion re-push + closed-set skip),
     so A* returns the OPTIMAL path and never expands a node twice (P0).

Django-free / network-free: the env lookup, POI lookup and (where needed) the cost
and neighbor functions are stubbed, mirroring test_astar_distance_tolerance.py.
"""

import math

import pytest

from evaluations import environmental_astar as ea


# Env stub that makes the green/preference rewards DOMINATE every penalty, so the
# floor is the only thing keeping the arc at/above the physical distance.
_GREEN_LOW_PENALTY_ENV = {
    'airQuality': 1.0, 'temperature': 22.0, 'humidity': 50.0,
    'noise': 1.0, 'slope': 0.0, 'greenSpace': 10.0, 'weather': 1.0,
    'trafficDensity': 0.0, 'greenVisibility': 1.0,
    'emergencyAccessibility': 1.0, 'surfaceQuality': 0.0, 'sensoryLoad': 0.0,
}

_NEUTRAL_ENV = {
    'airQuality': 5.0, 'temperature': 22.0, 'humidity': 50.0,
    'noise': 4.0, 'slope': 3.0, 'greenSpace': 3.0, 'weather': 1.0,
    'trafficDensity': 0.0, 'greenVisibility': 0.3,
    'emergencyAccessibility': 0.7, 'surfaceQuality': 0.3, 'sensoryLoad': 0.4,
}


# --------------------------------------------------------------------------- #
# 1) Arc cost >= physical distance, never negative (P0: no negative weights)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('condition', ['respiratory', 'cardiac', 'mobility', 'mental'])
def test_arc_cost_never_below_physical_distance(monkeypatch, condition):
    monkeypatch.setattr(ea, '_get_env', lambda lat, lon: dict(_GREEN_LOW_PENALTY_ENV))

    current = {'lat': 44.6400, 'lon': 10.9200}
    neighbor = {'lat': 44.6410, 'lon': 10.9205}
    distance = ea.haversine_m(current, neighbor)
    patient = ea.PATIENT_CONDITIONS[condition]

    # Pile on every reward: huge positive preference weights, max green scale, and a
    # POI sitting exactly on the neighbor (distance 0 => maximum POI reward). Under
    # the old (buggy) code these would drive the edge well below `distance`/negative.
    prefs = {'nature': 100, 'hospital': 100, 'entertainment': 100,
             'nightlife': 100, 'tourism': 100}
    poi_lists = {cat: [(neighbor['lat'], neighbor['lon'])]
                 for cat in ('nature', 'hospital', 'entertainment', 'nightlife', 'tourism')}

    for current_g in (0.0, 123.4):
        cost = ea.calculate_edge_cost(
            current, neighbor, current_g, patient,
            preferences=prefs, poi_lists=poi_lists,
            green_reward_scale=ea.tolerance_green_scale(10),
        )
        arc = cost - current_g
        # The defining P0 invariant: arc never below the physical distance ...
        assert arc >= distance - 1e-9, f"{condition}: arc {arc} < distance {distance}"
        # ... and with rewards >> penalties it clamps exactly to the floor.
        assert arc == pytest.approx(distance)
        # Total cost monotonic and non-negative (no negative weights).
        assert cost >= current_g
        assert cost >= 0.0


def test_default_condition_arc_equals_distance(monkeypatch):
    monkeypatch.setattr(ea, '_get_env', lambda lat, lon: dict(_NEUTRAL_ENV))
    current = {'lat': 44.6400, 'lon': 10.9200}
    neighbor = {'lat': 44.6410, 'lon': 10.9200}
    cost = ea.calculate_edge_cost(current, neighbor, 0.0, ea.PATIENT_CONDITIONS['default'])
    assert cost == pytest.approx(ea.haversine_m(current, neighbor))


# --------------------------------------------------------------------------- #
# 2) force_exact_endpoints: exact A/B (TODO5-algo)
# --------------------------------------------------------------------------- #

def test_force_exact_endpoints_empty_path():
    start = {'lat': 44.64, 'lon': 10.92}
    goal = {'lat': 44.65, 'lon': 10.93}
    out = ea.force_exact_endpoints([], start, goal)
    assert out == [{'lat': 44.64, 'lon': 10.92}, {'lat': 44.65, 'lon': 10.93}]


def test_force_exact_endpoints_appends_offgrid_endpoints():
    start = {'lat': 44.6400, 'lon': 10.9200}
    goal = {'lat': 44.6500, 'lon': 10.9300}
    # Grid corridor that starts/ends NEAR but not AT the true endpoints (> 0.5 m off).
    path = [
        {'lat': 44.6401, 'lon': 10.9201},
        {'lat': 44.6450, 'lon': 10.9250},
        {'lat': 44.6499, 'lon': 10.9299},
    ]
    out = ea.force_exact_endpoints(path, start, goal)
    assert out[0] == {'lat': 44.6400, 'lon': 10.9200}
    assert out[-1] == {'lat': 44.6500, 'lon': 10.9300}
    # off-grid endpoints are PREPENDED/APPENDED (corridor preserved in the middle)
    assert len(out) == len(path) + 2
    assert out[1:-1] == path


def test_force_exact_endpoints_snaps_close_endpoints():
    start = {'lat': 44.6400, 'lon': 10.9200}
    goal = {'lat': 44.6500, 'lon': 10.9300}
    # First/last nodes within 0.5 m of the true endpoints => snapped in place.
    near_start = {'lat': 44.64000001, 'lon': 10.92000001}
    near_goal = {'lat': 44.65000001, 'lon': 10.93000001}
    assert ea.haversine_m(near_start, start) <= ea._ENDPOINT_SNAP_TOLERANCE_M
    assert ea.haversine_m(near_goal, goal) <= ea._ENDPOINT_SNAP_TOLERANCE_M
    path = [near_start, {'lat': 44.645, 'lon': 10.925}, near_goal]
    out = ea.force_exact_endpoints(path, start, goal)
    assert len(out) == len(path)  # snapped, not duplicated
    assert out[0] == {'lat': 44.6400, 'lon': 10.9200}
    assert out[-1] == {'lat': 44.6500, 'lon': 10.9300}


def test_find_optimal_route_returns_exact_endpoints(monkeypatch):
    monkeypatch.setattr(ea, '_get_env', lambda lat, lon: dict(_NEUTRAL_ENV))
    monkeypatch.setattr(ea, 'get_poi_lists_for_grid', lambda grid: {})

    start_lat, start_lon = 44.6400, 10.9200
    end_lat, end_lon = 44.6450, 10.9250
    res = ea.find_optimal_route(
        start_lat, start_lon, end_lat, end_lon,
        condition='respiratory', grid_resolution_m=100.0,
    )
    assert res['goal_reached'] is True
    path = res['path']
    assert path[0] == {'lat': start_lat, 'lon': start_lon}
    assert path[-1] == {'lat': end_lat, 'lon': end_lon}


# --------------------------------------------------------------------------- #
# 3) Decrease-key correctness (P0): optimal result + no double expansion
# --------------------------------------------------------------------------- #

def test_decrease_key_returns_optimal_on_adversarial_graph(monkeypatch):
    """Hand-built graph where a node's g improves AFTER it is on the open heap.

    Optimal: S -> X -> N -> M -> G  (1 + 0.5 + 0.1 + 0.1 = 1.7)
    The buggy "don't re-push on improvement" decrease-key keeps N stuck at its
    first (worse) priority, so M is closed via the expensive S->X->M (=4) corridor
    before N is expanded, and N->M (=1.6) is then dropped by the closed-set skip,
    yielding the SUB-OPTIMAL 4.1. The fix re-pushes N at 1.5 so M is relaxed in
    time and the optimal 1.7 wins.
    """
    nodes = {
        'S': {'lat': 45.000000, 'lon': 9.000000},
        'X': {'lat': 45.001000, 'lon': 9.000000},
        'N': {'lat': 45.002000, 'lon': 9.000000},
        'M': {'lat': 45.003000, 'lon': 9.000000},
        'G': {'lat': 45.004000, 'lon': 9.000000},
    }
    id_to_label = {ea._node_id(n): label for label, n in nodes.items()}
    adjacency = {'S': ['X', 'N'], 'X': ['N', 'M'], 'N': ['M'], 'M': ['G'], 'G': []}
    edge_weight = {
        ('S', 'X'): 1.0, ('S', 'N'): 10.0,
        ('X', 'N'): 0.5, ('X', 'M'): 3.0,
        ('N', 'M'): 0.1, ('M', 'G'): 0.1,
    }

    def fake_grid(start, goal, resolution_m=100.0, distance_tolerance=1.0):
        return [nodes['X'], nodes['N'], nodes['M'], nodes['G']]

    def fake_neighbors(node, grid, resolution_m):
        label = id_to_label[ea._node_id(node)]
        return [nodes[n] for n in adjacency[label]]

    def fake_edge_cost(current, neighbor, current_g, patient, *args, **kwargs):
        c = id_to_label[ea._node_id(current)]
        n = id_to_label[ea._node_id(neighbor)]
        return current_g + edge_weight[(c, n)]

    monkeypatch.setattr(ea, 'create_search_grid', fake_grid)
    monkeypatch.setattr(ea, '_adaptive_resolution',
                        lambda start, goal, base=100.0, distance_tolerance=1.0: 100.0)
    monkeypatch.setattr(ea, 'get_poi_lists_for_grid', lambda grid: {})
    monkeypatch.setattr(ea, 'get_neighbors', fake_neighbors)
    monkeypatch.setattr(ea, 'calculate_edge_cost', fake_edge_cost)
    monkeypatch.setattr(ea, 'estimate_heuristic', lambda node, goal: 0.0)  # Dijkstra
    monkeypatch.setattr(ea, 'is_goal_reached',
                        lambda node, goal: ea._node_id(node) == ea._node_id(nodes['G']))

    res = ea.find_optimal_route(
        nodes['S']['lat'], nodes['S']['lon'],
        nodes['G']['lat'], nodes['G']['lon'],
        condition='respiratory', grid_resolution_m=100.0,
    )

    assert res['goal_reached'] is True
    # OPTIMAL cost (would be 4.1 with the broken decrease-key).
    assert res['astar_cost'] == pytest.approx(1.7)
    labels = [id_to_label[ea._node_id(p)] for p in res['path']]
    assert labels == ['S', 'X', 'N', 'M', 'G']


def test_no_node_expanded_twice(monkeypatch):
    """Lazy-deletion: a node re-pushed with a better priority must NOT be expanded
    twice — the stale heap copy is skipped via the closed-set check on pop."""
    monkeypatch.setattr(ea, '_get_env', lambda lat, lon: dict(_NEUTRAL_ENV))
    monkeypatch.setattr(ea, 'get_poi_lists_for_grid', lambda grid: {})

    original_get_neighbors = ea.get_neighbors
    expanded = []

    def counting_get_neighbors(node, grid, resolution_m):
        expanded.append(ea._node_id(node))
        return original_get_neighbors(node, grid, resolution_m)

    monkeypatch.setattr(ea, 'get_neighbors', counting_get_neighbors)

    res = ea.find_optimal_route(
        44.6400, 10.9200, 44.6470, 10.9270,
        condition='mental', grid_resolution_m=100.0,
    )
    assert res['goal_reached'] is True
    # Every expanded node id is unique => no stale duplicate was ever re-expanded.
    assert len(expanded) == len(set(expanded))
