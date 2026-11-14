from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from weather.config import load_settings
from weather.db import connect, init_schema
from weather.exporter import build_excel

SETTINGS = load_settings()
STATIC_DIR = Path(__file__).with_name("static")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_schema(SETTINGS.database_url)
    yield


app = FastAPI(
    title="Tiempo GrowerLabs",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with connect(SETTINGS.database_url) as connection:
            connection.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict:
    with connect(SETTINGS.database_url, rows=True) as connection:
        run = connection.execute(
            """
            SELECT started_at, finished_at, status, fetched_records,
                   inserted_records, error_message
            FROM collection_runs ORDER BY run_id DESC LIMIT 1
            """
        ).fetchone()
        counts = connection.execute(
            """
            SELECT (SELECT count(*) FROM stations) AS stations,
                   (SELECT count(*) FROM variables) AS variables,
                   (SELECT count(*) FROM observations) AS observations,
                   (SELECT max(observed_at) FROM observations) AS latest_observation
            """
        ).fetchone()
    return {"collector": run, "database": counts}


@app.get("/api/stations")
def stations() -> list[dict]:
    with connect(SETTINGS.database_url, rows=True) as connection:
        return list(
            connection.execute(
                """
                SELECT s.station_key, s.name, s.public_name, s.code_omm,
                       s.code_oaci, s.latitude, s.longitude, s.altitude_m,
                       max(o.observed_at) AS latest_observation,
                       count(DISTINCT o.variable_id) AS variable_count
                FROM stations s
                LEFT JOIN observations o USING (station_key)
                GROUP BY s.station_key
                HAVING count(o.*) > 0
                ORDER BY coalesce(s.public_name, s.name)
                """
            ).fetchall()
        )


@app.get("/api/stations/{station_key}/variables")
def station_variables(station_key: str) -> list[dict]:
    with connect(SETTINGS.database_url, rows=True) as connection:
        rows = connection.execute(
            """
            SELECT v.variable_id, v.name, v.unit,
                   min(o.observed_at) AS first_observation,
                   max(o.observed_at) AS latest_observation,
                   count(*) AS observation_count
            FROM observations o
            JOIN variables v USING (variable_id)
            WHERE o.station_key = %s
            GROUP BY v.variable_id
            ORDER BY v.name
            """,
            (station_key,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="station not found")
    return list(rows)


def _parse_variable_ids(value: str) -> list[int]:
    try:
        result = sorted({int(item) for item in value.split(",") if item.strip()})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="variables inválidas") from exc
    if not result or len(result) > 4:
        raise HTTPException(status_code=422, detail="seleccione entre 1 y 4 variables")
    return result


@app.get("/api/series")
def series(
    station: str = Query(min_length=1, max_length=100),
    variables: str = Query(min_length=1, max_length=100),
    hours: int = Query(default=24, ge=1, le=24 * 90),
) -> dict:
    variable_ids = _parse_variable_ids(variables)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with connect(SETTINGS.database_url, rows=True) as connection:
        rows = connection.execute(
            """
            SELECT o.variable_id, v.name, v.unit, o.observed_at,
                   o.numeric_value, o.text_value
            FROM observations o
            JOIN variables v USING (variable_id)
            WHERE o.station_key = %s
              AND o.variable_id = ANY(%s)
              AND o.observed_at >= %s
            ORDER BY o.observed_at ASC
            LIMIT %s
            """,
            (station, variable_ids, since, SETTINGS.series_max_points),
        ).fetchall()
    grouped: dict[int, dict] = defaultdict(lambda: {"points": []})
    for row in rows:
        group = grouped[row["variable_id"]]
        group.update(
            {
                "variable_id": row["variable_id"],
                "name": row["name"],
                "unit": row["unit"],
            }
        )
        group["points"].append(
            {
                "observed_at": row["observed_at"],
                "value": row["numeric_value"],
                "text": row["text_value"],
            }
        )
    return {
        "station_key": station,
        "hours": hours,
        "series": list(grouped.values()),
        "truncated": len(rows) >= SETTINGS.series_max_points,
    }


@app.get("/api/export.xlsx")
def export_excel(
    station: str = Query(min_length=1, max_length=100),
    variables: str = Query(min_length=1, max_length=100),
    hours: int = Query(default=24, ge=1, le=24 * 90),
) -> Response:
    variable_ids = _parse_variable_ids(variables)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with connect(SETTINGS.database_url, rows=True) as connection:
        station_row = connection.execute(
            """
            SELECT station_key, name, public_name, code_omm, code_oaci,
                   latitude, longitude, altitude_m
            FROM stations WHERE station_key = %s
            """,
            (station,),
        ).fetchone()
        variable_rows = list(
            connection.execute(
                """
                SELECT variable_id, name, unit, description
                FROM variables WHERE variable_id = ANY(%s)
                ORDER BY name
                """,
                (variable_ids,),
            ).fetchall()
        )
        rows = list(
            connection.execute(
                """
                SELECT variable_id, observed_at, numeric_value, text_value
                FROM observations
                WHERE station_key = %s AND variable_id = ANY(%s)
                  AND observed_at >= %s
                ORDER BY observed_at ASC
                LIMIT %s
                """,
                (station, variable_ids, since, SETTINGS.series_max_points),
            ).fetchall()
        )
    if not station_row:
        raise HTTPException(status_code=404, detail="station not found")
    if not rows:
        raise HTTPException(status_code=404, detail="no hay datos para exportar")
    generated_at = datetime.now(timezone.utc)
    content = build_excel(dict(station_row), variable_rows, rows, generated_at)
    safe_station = "".join(
        character if character.isalnum() else "-" for character in station.lower()
    ).strip("-")
    filename = f"inumet_{safe_station}_{generated_at:%Y-%m-%d_%H-%M-%S}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/latest")
def latest(station: str = Query(min_length=1, max_length=100)) -> list[dict]:
    with connect(SETTINGS.database_url, rows=True) as connection:
        return list(
            connection.execute(
                """
                SELECT DISTINCT ON (o.variable_id)
                    o.variable_id, v.name, v.unit, o.observed_at,
                    o.numeric_value, o.text_value
                FROM observations o
                JOIN variables v USING (variable_id)
                WHERE o.station_key = %s
                ORDER BY o.variable_id, o.observed_at DESC
                """,
                (station,),
            ).fetchall()
        )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
