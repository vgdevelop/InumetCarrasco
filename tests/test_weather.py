from datetime import timezone

from weather.inumet import (
    iter_observations,
    parse_source_datetime,
    split_value,
    station_key,
)


def test_station_key_prefers_stable_string_id():
    assert station_key({"id": 7, "idStr": "carrasco"}) == "CARRASCO"


def test_parse_source_datetime_converts_uruguay_time_to_utc():
    result = parse_source_datetime("2026-08-15T12:00:00", "America/Montevideo")
    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.hour == 15


def test_split_value_supports_decimal_comma_and_text():
    assert split_value("12,5") == (12.5, None)
    assert split_value("TRAZA") == (None, "TRAZA")


def test_iter_observations_handles_all_stations():
    data = {
        "estaciones": [
            {"id": 1, "idStr": "UNO"},
            {"id": 2, "idStr": "DOS"},
        ],
        "variables": [{"id": 47, "nombre": "Temperatura"}],
        "fechas": ["2026-08-15T12:00:00"],
        "observaciones": [
            {"iFechas": [0], "datos": [[20.1], [21.4]]},
        ],
    }
    rows = list(iter_observations(data, "America/Montevideo"))
    assert [row["station_key"] for row in rows] == ["UNO", "DOS"]
    assert [row["numeric_value"] for row in rows] == [20.1, 21.4]
