from datetime import datetime, timezone

import pandas as pd
import pytest

from script import (
    build_filtered_json,
    direction_to_cardinal,
    find_carrasco_station,
    numeric_or_original,
    parse_datetime,
)


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [(0, "N"), (45, "NE"), (90, "E"), (180, "S"), (270, "W"), (360, "N")],
)
def test_direction_to_cardinal(degrees, expected):
    assert direction_to_cardinal(degrees) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12,5", 12.5), (" TRAZA ", "TRAZA"), ("", None)],
)
def test_numeric_or_original(value, expected):
    result = numeric_or_original(value)
    assert pd.isna(result) if expected is None else result == expected


def test_find_carrasco_station_prefers_stable_id():
    stations = [{"idStr": "OTRA"}, {"idStr": "CARRASCO", "id": 42}]
    index, station = find_carrasco_station(stations)
    assert index == 1
    assert station["id"] == 42


def test_parse_datetime_invalid_value_returns_nat():
    assert pd.isna(parse_datetime("fecha-invalida"))


def test_build_filtered_json_serializes_values():
    frame = pd.DataFrame(
        [
            {
                "FechaHora": pd.Timestamp("2026-01-01T12:00:00"),
                "VariableID": 47,
                "Variable": "Temperatura",
                "Unidad": "°C",
                "PeriodicidadID": 1,
                "Valor": 24.5,
                "ValorNumerico": 24.5,
                "DireccionCardinal": None,
            }
        ]
    )
    result = build_filtered_json(
        {"idStr": "CARRASCO"}, frame, datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert result["cantidad_registros"] == 1
    assert result["telemetria"][0]["valor"] == 24.5
