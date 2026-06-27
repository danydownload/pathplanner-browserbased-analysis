#!/usr/bin/env python
"""Ensure a local OSM POI/walkability SQLite database exists.

This script is intended for server bootstrap/deploys. It is idempotent: when the
configured DB already exists and passes basic integrity/count checks, it exits
without rebuilding. When the DB is missing, it imports from the configured PBF
into a temporary file and atomically replaces the target only after success.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluations.local_osm_poi_service import build_local_osm_db


def _bool_env(name: str, default: bool = False) -> bool:
    value = (os.getenv(name) or '').strip().lower()
    if not value:
        return default
    return value in {'1', 'true', 'yes', 'on'}


def _default_db_path() -> Path | None:
    configured = (os.getenv('LOCAL_OSM_POI_DB') or '').strip()
    if configured:
        return Path(configured).expanduser()
    return ROOT / 'runtime' / 'local_osm_pois' / 'italy.sqlite3'


def _default_pbf_path() -> Path | None:
    configured = (os.getenv('LOCAL_OSM_PBF_PATH') or '').strip()
    if configured:
        return Path(configured).expanduser()
    candidate = ROOT / 'pbf' / 'italy-260626.osm.pbf'
    return candidate if candidate.exists() else None


def _db_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(str(db_path)) as conn:
        quick_check = conn.execute('PRAGMA quick_check').fetchone()[0]
        if quick_check != 'ok':
            raise sqlite3.DatabaseError(f'quick_check failed: {quick_check}')
        return {
            'poi': int(conn.execute('SELECT COUNT(*) FROM poi').fetchone()[0]),
            'walkability_feature': int(
                conn.execute('SELECT COUNT(*) FROM walkability_feature').fetchone()[0]
            ),
        }


def check_db(
    db_path: Path,
    *,
    include_walkability: bool,
    min_poi_rows: int,
    min_walkability_rows: int,
) -> dict[str, Any]:
    if not db_path.exists():
        return {'ok': False, 'reason': 'missing', 'db_path': str(db_path)}
    try:
        counts = _db_counts(db_path)
    except (sqlite3.Error, OSError) as exc:
        return {
            'ok': False,
            'reason': 'unreadable',
            'error': str(exc),
            'db_path': str(db_path),
        }
    if counts['poi'] < min_poi_rows:
        return {
            'ok': False,
            'reason': 'too_few_pois',
            'counts': counts,
            'db_path': str(db_path),
        }
    if include_walkability and counts['walkability_feature'] < min_walkability_rows:
        return {
            'ok': False,
            'reason': 'too_few_walkability_features',
            'counts': counts,
            'db_path': str(db_path),
        }
    return {'ok': True, 'counts': counts, 'db_path': str(db_path)}


def _cleanup_temp(db_path: Path) -> Path:
    timestamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    temp_path = db_path.with_name(f'.{db_path.name}.{timestamp}.tmp')
    for candidate in (
        temp_path,
        temp_path.with_name(temp_path.name + '-wal'),
        temp_path.with_name(temp_path.name + '-shm'),
    ):
        if candidate.exists():
            candidate.unlink()
    return temp_path


def ensure_db(
    *,
    db_path: Path,
    pbf_path: Path,
    include_walkability: bool,
    min_poi_rows: int,
    min_walkability_rows: int,
    force: bool = False,
) -> dict[str, Any]:
    db_path = db_path.expanduser()
    pbf_path = pbf_path.expanduser()
    existing = check_db(
        db_path,
        include_walkability=include_walkability,
        min_poi_rows=min_poi_rows,
        min_walkability_rows=min_walkability_rows,
    )
    if existing['ok'] and not force:
        return {'action': 'already_exists', **existing}
    if not pbf_path.exists():
        raise FileNotFoundError(f'Missing PBF file: {pbf_path}')

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _cleanup_temp(db_path)
    result = build_local_osm_db(
        pbf_path,
        temp_path,
        include_walkability=include_walkability,
    )
    built = check_db(
        temp_path,
        include_walkability=include_walkability,
        min_poi_rows=min_poi_rows,
        min_walkability_rows=min_walkability_rows,
    )
    if not built['ok']:
        raise RuntimeError(f'Built DB failed validation: {built}')

    backup_path = None
    if db_path.exists():
        backup_path = db_path.with_name(
            f'{db_path.stem}.backup.{time.strftime("%Y%m%d-%H%M%S", time.gmtime())}{db_path.suffix}'
        )
        db_path.replace(backup_path)
    temp_path.replace(db_path)
    return {
        'action': 'rebuilt' if force else 'created',
        'db_path': str(db_path),
        'pbf_path': str(pbf_path),
        'include_walkability': include_walkability,
        'backup_path': str(backup_path) if backup_path else None,
        'build': result,
        'validation': {**built, 'db_path': str(db_path)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=_default_db_path(), help='Target SQLite DB path')
    parser.add_argument('--pbf', type=Path, default=_default_pbf_path(), help='Input OSM PBF path')
    parser.add_argument(
        '--mode',
        choices=('full', 'poi-only'),
        default=(os.getenv('LOCAL_OSM_POI_BUILD_MODE') or 'full'),
        help='Build full POI+walkability DB or POI-only DB',
    )
    parser.add_argument('--force', action='store_true', default=_bool_env('LOCAL_OSM_POI_FORCE_REBUILD'))
    parser.add_argument('--min-poi-rows', type=int, default=int(os.getenv('LOCAL_OSM_POI_MIN_ROWS', '1')))
    parser.add_argument(
        '--min-walkability-rows',
        type=int,
        default=int(os.getenv('LOCAL_OSM_WALKABILITY_MIN_ROWS', '1')),
    )
    args = parser.parse_args()

    if args.db is None:
        parser.error('--db or LOCAL_OSM_POI_DB is required')
    if args.pbf is None:
        parser.error('--pbf or LOCAL_OSM_PBF_PATH is required when the default PBF is unavailable')

    result = ensure_db(
        db_path=args.db,
        pbf_path=args.pbf,
        include_walkability=args.mode == 'full',
        min_poi_rows=args.min_poi_rows,
        min_walkability_rows=args.min_walkability_rows,
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
