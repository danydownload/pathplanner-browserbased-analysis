from pathlib import Path

from evaluations.local_osm_poi_service import init_db
from scripts import ensure_local_osm_poi_db


def _insert_rows(db_path: Path, *, poi_count: int = 1, walkability_count: int = 1) -> None:
    import sqlite3

    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        for index in range(poi_count):
            conn.execute(
                """
                INSERT INTO poi (id, osm_type, osm_id, category, name, kind, lat, lon, tags)
                VALUES (?, 'node', ?, 'parks', 'Park', 'park', 44.0, 10.0, '{}')
                """,
                (f'poi/{index}', index),
            )
        for index in range(walkability_count):
            conn.execute(
                """
                INSERT INTO walkability_feature
                    (id, osm_type, osm_id, category, name, kind, lat, lon, tags)
                VALUES (?, 'way', ?, 'surface', NULL, 'asphalt', 44.0, 10.0, '{}')
                """,
                (f'walk/{index}', index),
            )
        conn.commit()


def test_check_db_accepts_valid_full_db(tmp_path):
    db_path = tmp_path / 'pois.sqlite3'
    _insert_rows(db_path, poi_count=2, walkability_count=3)

    result = ensure_local_osm_poi_db.check_db(
        db_path,
        include_walkability=True,
        min_poi_rows=1,
        min_walkability_rows=1,
    )

    assert result['ok'] is True
    assert result['counts'] == {'poi': 2, 'walkability_feature': 3}


def test_check_db_rejects_missing_walkability_for_full_mode(tmp_path):
    db_path = tmp_path / 'pois.sqlite3'
    _insert_rows(db_path, poi_count=2, walkability_count=0)

    result = ensure_local_osm_poi_db.check_db(
        db_path,
        include_walkability=True,
        min_poi_rows=1,
        min_walkability_rows=1,
    )

    assert result['ok'] is False
    assert result['reason'] == 'too_few_walkability_features'


def test_ensure_db_skips_existing_valid_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'pois.sqlite3'
    pbf_path = tmp_path / 'extract.osm.pbf'
    pbf_path.write_bytes(b'fake pbf')
    _insert_rows(db_path, poi_count=1, walkability_count=1)

    def fail_build(*args, **kwargs):
        raise AssertionError('build should not run')

    monkeypatch.setattr(ensure_local_osm_poi_db, 'build_local_osm_db', fail_build)

    result = ensure_local_osm_poi_db.ensure_db(
        db_path=db_path,
        pbf_path=pbf_path,
        include_walkability=True,
        min_poi_rows=1,
        min_walkability_rows=1,
    )

    assert result['action'] == 'already_exists'


def test_ensure_db_builds_missing_db_atomically(tmp_path, monkeypatch):
    db_path = tmp_path / 'pois.sqlite3'
    pbf_path = tmp_path / 'extract.osm.pbf'
    pbf_path.write_bytes(b'fake pbf')

    def fake_build(pbf, db, *, include_walkability):
        assert pbf == pbf_path
        assert include_walkability is True
        assert db != db_path
        _insert_rows(db, poi_count=4, walkability_count=5)
        return {
            'db_path': str(db),
            'pbf_path': str(pbf),
            'include_walkability': include_walkability,
            'counts': {'poi': 4, 'walkability_feature': 5},
        }

    monkeypatch.setattr(ensure_local_osm_poi_db, 'build_local_osm_db', fake_build)

    result = ensure_local_osm_poi_db.ensure_db(
        db_path=db_path,
        pbf_path=pbf_path,
        include_walkability=True,
        min_poi_rows=1,
        min_walkability_rows=1,
    )

    assert result['action'] == 'created'
    assert db_path.exists()
    assert result['validation']['counts'] == {'poi': 4, 'walkability_feature': 5}
