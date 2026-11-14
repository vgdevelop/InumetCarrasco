from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

from weather.exporter import build_excel


def test_excel_contains_compatible_sheets_and_filtered_data() -> None:
    station = {
        "station_key": "CARRASCO",
        "name": "Carrasco",
        "public_name": "Carrasco",
        "code_omm": "86580",
        "code_oaci": "SUMU",
        "latitude": -34.83,
        "longitude": -56.01,
        "altitude_m": 32.88,
    }
    variables = [
        {
            "variable_id": 47,
            "name": "Temperatura",
            "unit": "°C",
            "description": "Temperatura del aire",
        }
    ]
    rows = [
        {
            "variable_id": 47,
            "observed_at": datetime(2026, 8, 15, 18, tzinfo=timezone.utc),
            "numeric_value": 18.5,
            "text_value": None,
        },
        {
            "variable_id": 47,
            "observed_at": datetime(2026, 8, 15, 19, tzinfo=timezone.utc),
            "numeric_value": 19.2,
            "text_value": None,
        },
    ]

    content = build_excel(station, variables, rows, datetime.now(timezone.utc))

    assert content.startswith(b"PK")
    with ZipFile(BytesIO(content)) as workbook:
        workbook_xml = workbook.read("xl/workbook.xml").decode()
        shared_strings = workbook.read("xl/sharedStrings.xml").decode()
        chart_xml = workbook.read("xl/charts/chart1.xml").decode()
    for sheet in (
        "Telemetria",
        "Datos por Hora",
        "Resumen",
        "Estacion y Variables",
        "Series Graficas",
        "Graficas",
    ):
        assert sheet in workbook_xml
    assert 'name="Series Graficas" sheetId="5" state="hidden"' in workbook_xml
    assert "Temperatura" in shared_strings
    assert "Carrasco" in shared_strings
    assert "<c:scatterChart>" in chart_xml
    assert "<c:lineChart>" not in chart_xml
    assert "'Series Graficas'!$A$2:$A$3" in chart_xml
    assert "'Series Graficas'!$B$2:$B$3" in chart_xml
    assert 'formatCode="dd/mm/yyyy hh:mm"' in chart_xml
