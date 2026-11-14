from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

REQUIRED_KEYS = {"estaciones", "variables", "fechas", "observaciones"}


def fetch_dataset(url: str, timeout: int) -> dict[str, Any]:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "GrowerLabs-Tiempo/1.0",
        },
    )
    response.raise_for_status()
    data = response.json()
    missing = REQUIRED_KEYS.difference(data)
    if missing:
        raise RuntimeError(f"La respuesta de INUMET no contiene: {sorted(missing)}")
    if len(data["variables"]) != len(data["observaciones"]):
        raise RuntimeError("Variables y observaciones tienen longitudes diferentes")
    return data


def station_key(station: dict[str, Any]) -> str:
    for field in ("idStr", "codigoOMM", "idOACI", "id"):
        value = station.get(field)
        if value not in (None, ""):
            return str(value).strip().upper()
    raise RuntimeError("Una estación no contiene identificador estable")


def parse_source_datetime(value: Any, timezone_name: str) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=ZoneInfo(timezone_name))
    return result.astimezone(timezone.utc)


def split_value(value: Any) -> tuple[float | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, None if value is None else str(value).lower()
    if isinstance(value, (int, float)):
        numeric = float(value)
        return (None, None) if math.isnan(numeric) else (numeric, None)
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "-"}:
        return None, None
    try:
        return float(text.replace(",", ".")), None
    except ValueError:
        return None, text


def iter_observations(
    data: dict[str, Any], timezone_name: str
) -> Iterator[dict[str, Any]]:
    stations = data["estaciones"]
    dates = data["fechas"]
    for variable, observation in zip(
        data["variables"], data["observaciones"], strict=True
    ):
        observation = observation or {}
        date_indexes = observation.get("iFechas") or []
        station_data = observation.get("datos") or []
        for station_index, values in enumerate(station_data):
            if station_index >= len(stations) or not isinstance(values, list):
                continue
            station = stations[station_index]
            for value_index, raw_value in enumerate(values):
                if value_index >= len(date_indexes) or raw_value is None:
                    continue
                date_index = date_indexes[value_index]
                if not isinstance(date_index, int) or not 0 <= date_index < len(dates):
                    continue
                observed_at = parse_source_datetime(dates[date_index], timezone_name)
                if observed_at is None:
                    continue
                numeric_value, text_value = split_value(raw_value)
                if numeric_value is None and text_value is None:
                    continue
                yield {
                    "station_key": station_key(station),
                    "variable_id": int(variable["id"]),
                    "observed_at": observed_at,
                    "numeric_value": numeric_value,
                    "text_value": text_value,
                    "raw_value": raw_value,
                }
