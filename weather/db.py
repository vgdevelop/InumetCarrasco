from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(database_url: str, *, rows: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        database_url,
        row_factory=dict_row if rows else None,
        connect_timeout=10,
    )


def init_schema(database_url: str) -> None:
    with connect(database_url) as connection:
        connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def store_dataset(
    database_url: str,
    stations: list[dict[str, Any]],
    variables: list[dict[str, Any]],
    observations: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    from weather.inumet import station_key

    observation_rows = list(observations)
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO stations (
                    station_key, source_id, name, public_name, code_omm,
                    code_oaci, latitude, longitude, altitude_m, active, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (station_key) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    name = EXCLUDED.name,
                    public_name = EXCLUDED.public_name,
                    code_omm = EXCLUDED.code_omm,
                    code_oaci = EXCLUDED.code_oaci,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    altitude_m = EXCLUDED.altitude_m,
                    active = EXCLUDED.active,
                    metadata = EXCLUDED.metadata,
                    last_seen_at = now()
                """,
                [
                    (
                        station_key(item),
                        str(item.get("id")) if item.get("id") is not None else None,
                        item.get("nombre")
                        or item.get("displayName")
                        or station_key(item),
                        item.get("displayNamePublic"),
                        item.get("codigoOMM"),
                        item.get("idOACI"),
                        _number(item.get("latitud")),
                        _number(item.get("longitud")),
                        _number(item.get("altitud")),
                        str(item.get("estado", "")).lower()
                        not in {"false", "0", "inactiva"},
                        json.dumps(item, ensure_ascii=False),
                    )
                    for item in stations
                ],
            )
            cursor.executemany(
                """
                INSERT INTO variables (
                    variable_id, source_key, name, unit, description, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (variable_id) DO UPDATE SET
                    source_key = EXCLUDED.source_key,
                    name = EXCLUDED.name,
                    unit = EXCLUDED.unit,
                    description = EXCLUDED.description,
                    metadata = EXCLUDED.metadata,
                    last_seen_at = now()
                """,
                [
                    (
                        int(item["id"]),
                        item.get("idStr"),
                        item.get("nombre") or item.get("idStr") or str(item["id"]),
                        item.get("unidad"),
                        item.get("descripVariab"),
                        json.dumps(item, ensure_ascii=False),
                    )
                    for item in variables
                ],
            )
            before = connection.execute("SELECT count(*) FROM observations").fetchone()[
                0
            ]
            cursor.executemany(
                """
                INSERT INTO observations (
                    station_key, variable_id, observed_at,
                    numeric_value, text_value, raw_value
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (station_key, variable_id, observed_at) DO NOTHING
                """,
                [
                    (
                        item["station_key"],
                        item["variable_id"],
                        item["observed_at"],
                        item["numeric_value"],
                        item["text_value"],
                        json.dumps(item["raw_value"]),
                    )
                    for item in observation_rows
                ],
            )
            after = connection.execute("SELECT count(*) FROM observations").fetchone()[
                0
            ]
    return len(observation_rows), after - before


def begin_run(database_url: str) -> int:
    with connect(database_url) as connection:
        return connection.execute(
            """
            INSERT INTO collection_runs (started_at, status)
            VALUES (%s, 'running') RETURNING run_id
            """,
            (datetime.now(timezone.utc),),
        ).fetchone()[0]


def finish_run(
    database_url: str,
    run_id: int,
    status: str,
    fetched: int = 0,
    inserted: int = 0,
    error: str | None = None,
) -> None:
    with connect(database_url) as connection:
        connection.execute(
            """
            UPDATE collection_runs SET finished_at = now(), status = %s,
                fetched_records = %s, inserted_records = %s, error_message = %s
            WHERE run_id = %s
            """,
            (status, fetched, inserted, error[:500] if error else None, run_id),
        )
