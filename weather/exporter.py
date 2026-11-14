from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import xlsxwriter

URUGUAY_TIMEZONE = ZoneInfo("America/Montevideo")


def _excel_datetime(value: datetime) -> datetime:
    return value.astimezone(URUGUAY_TIMEZONE).replace(tzinfo=None)


def _clean_text(value: Any) -> str:
    return str(value or "").replace("_x000D_", " ").replace("\r", " ").strip()


def _axis_bounds(values: list[float]) -> tuple[float, float]:
    minimum, maximum = min(values), max(values)
    spread = maximum - minimum
    padding = (
        max(abs((minimum + maximum) / 2) * 0.01, 0.5)
        if spread == 0
        else max(spread * 0.1, 0.5)
    )
    raw_step = max((spread + 2 * padding) / 6, 0.1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 2.5:
        nice = 2.5
    elif normalized <= 5.5:
        nice = 5
    else:
        nice = 10
    step = nice * magnitude
    return math.floor((minimum - padding) / step) * step, math.ceil(
        (maximum + padding) / step
    ) * step


def _date_axis_interval_days(timestamps: list[datetime]) -> float:
    duration_hours = (
        (max(timestamps) - min(timestamps)).total_seconds() / 3600
        if len(timestamps) > 1
        else 1
    )
    if duration_hours <= 48:
        return 0.25
    if duration_hours <= 24 * 7:
        return 0.5
    if duration_hours <= 24 * 31:
        return 2
    return 7


def build_excel(
    station: dict[str, Any],
    variables: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    generated_at: datetime,
) -> bytes:
    """Create an INUMETCarrasco-compatible workbook for the active filters."""
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties({"title": "Telemetría INUMET", "company": "GrowerLabs"})
    title = workbook.add_format({"bold": True, "font_size": 16})
    subtitle = workbook.add_format({"italic": True, "font_size": 10})
    header = workbook.add_format(
        {"bold": True, "border": 1, "align": "center", "text_wrap": True}
    )
    date_format = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm"})
    number = workbook.add_format({"num_format": "0.00"})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    station_name = station.get("public_name") or station.get("name") or "Estación"
    variable_map = {int(item["variable_id"]): item for item in variables}
    ordered_rows = sorted(
        rows, key=lambda row: (row["observed_at"], row["variable_id"])
    )

    telemetry_headers = [
        "FechaHora",
        "VariableID",
        "Variable",
        "Unidad",
        "Valor",
        "ValorNumerico",
        "DireccionCardinal",
        "PeriodicidadID",
    ]
    ws = workbook.add_worksheet("Telemetria")
    ws.write("A1", f"Telemetría INUMET - {station_name}", title)
    ws.write(
        "A2",
        f"Generado: {generated_at.astimezone(URUGUAY_TIMEZONE):%d/%m/%Y %H:%M:%S %z}",
        subtitle,
    )
    for column, value in enumerate(telemetry_headers):
        ws.write(2, column, value, header)
    for row_index, row in enumerate(ordered_rows, start=3):
        variable = variable_map[int(row["variable_id"])]
        shown_value = (
            row["numeric_value"]
            if row["numeric_value"] is not None
            else row["text_value"]
        )
        ws.write_datetime(
            row_index, 0, _excel_datetime(row["observed_at"]), date_format
        )
        ws.write_number(row_index, 1, int(row["variable_id"]))
        ws.write(row_index, 2, variable["name"])
        ws.write(row_index, 3, variable.get("unit") or "")
        ws.write(row_index, 4, shown_value)
        if row["numeric_value"] is not None:
            ws.write_number(row_index, 5, float(row["numeric_value"]), number)
    ws.freeze_panes(3, 1)
    ws.autofilter(2, 0, max(3, len(ordered_rows) + 2), len(telemetry_headers) - 1)
    ws.set_column("A:A", 19, date_format)
    ws.set_column("B:B", 11)
    ws.set_column("C:C", 34)
    ws.set_column("D:H", 16)

    by_time: dict[datetime, dict[int, float]] = defaultdict(dict)
    for row in ordered_rows:
        if row["numeric_value"] is not None:
            by_time[row["observed_at"]][int(row["variable_id"])] = float(
                row["numeric_value"]
            )
    selected_ids = [int(item["variable_id"]) for item in variables]
    wide = workbook.add_worksheet("Datos por Hora")
    wide.write("A1", f"Datos de {station_name} por fecha/hora", title)
    wide.write(
        "A2", "Formato ancho para análisis, Power BI y nuevas gráficas.", subtitle
    )
    wide_headers = ["FechaHora"] + [variable_map[item]["name"] for item in selected_ids]
    for column, value in enumerate(wide_headers):
        wide.write(2, column, value, header)
    for row_index, observed_at in enumerate(sorted(by_time), start=3):
        wide.write_datetime(row_index, 0, _excel_datetime(observed_at), date_format)
        for column, variable_id in enumerate(selected_ids, start=1):
            value = by_time[observed_at].get(variable_id)
            if value is not None:
                wide.write_number(row_index, column, value, number)
    wide.freeze_panes(3, 1)
    wide.set_column("A:A", 19, date_format)
    wide.set_column(1, max(1, len(selected_ids)), 22, number)

    summary = workbook.add_worksheet("Resumen")
    summary.write("A1", f"Resumen - {station_name}", title)
    summary.write("A2", f"Registros filtrados: {len(ordered_rows)}", subtitle)
    summary_headers = [
        "VariableID",
        "Variable",
        "Unidad",
        "Registros",
        "Mínimo",
        "Máximo",
        "Promedio",
        "Último",
        "PrimeraFecha",
        "ÚltimaFecha",
    ]
    for column, value in enumerate(summary_headers):
        summary.write(4, column, value, header)
    for row_index, variable_id in enumerate(selected_ids, start=5):
        values = [
            row
            for row in ordered_rows
            if int(row["variable_id"]) == variable_id
            and row["numeric_value"] is not None
        ]
        numeric = [float(row["numeric_value"]) for row in values]
        variable = variable_map[variable_id]
        summary.write_row(
            row_index,
            0,
            [variable_id, variable["name"], variable.get("unit") or "", len(numeric)],
        )
        if numeric:
            for column, value in enumerate(
                [min(numeric), max(numeric), sum(numeric) / len(numeric), numeric[-1]],
                start=4,
            ):
                summary.write_number(row_index, column, value, number)
            summary.write_datetime(
                row_index, 8, _excel_datetime(values[0]["observed_at"]), date_format
            )
            summary.write_datetime(
                row_index,
                9,
                _excel_datetime(values[-1]["observed_at"]),
                date_format,
            )
    summary.set_column("A:A", 11)
    summary.set_column("B:B", 34)
    summary.set_column("C:H", 14)
    summary.set_column("I:J", 19, date_format)
    summary.freeze_panes(5, 0)

    metadata = workbook.add_worksheet("Estacion y Variables")
    metadata.write("A1", f"Estación {station_name}", title)
    station_rows = [
        ("Clave", station.get("station_key")),
        ("Nombre", station.get("name")),
        ("Nombre público", station.get("public_name")),
        ("Código OMM", station.get("code_omm")),
        ("OACI", station.get("code_oaci")),
        ("Latitud", station.get("latitude")),
        ("Longitud", station.get("longitude")),
        ("Altitud", station.get("altitude_m")),
        ("Fuente", "https://www.inumet.gub.uy/"),
    ]
    metadata.write_row(2, 0, ["Campo", "Valor"], header)
    for row_index, item in enumerate(station_rows, start=3):
        metadata.write_row(row_index, 0, item)
    variables_start = len(station_rows) + 6
    metadata.write(variables_start - 2, 0, "Variables exportadas", title)
    metadata.write_row(
        variables_start, 0, ["ID", "Nombre", "Unidad", "Descripción"], header
    )
    for row_index, variable in enumerate(variables, start=variables_start + 1):
        metadata.write_row(
            row_index,
            0,
            [
                variable["variable_id"],
                variable["name"],
                variable.get("unit") or "",
                _clean_text(variable.get("description")),
            ],
        )
    metadata.set_column("A:A", 24)
    metadata.set_column("B:B", 60, wrap)
    metadata.set_column("C:D", 28, wrap)

    chart_data = workbook.add_worksheet("Series Graficas")
    chart_data.hide()
    for series_index, variable_id in enumerate(selected_ids):
        date_column = series_index * 2
        value_column = date_column + 1
        chart_data.write(0, date_column, "FechaHora", header)
        chart_data.write(0, value_column, variable_map[variable_id]["name"], header)
        variable_values = [
            row
            for row in ordered_rows
            if int(row["variable_id"]) == variable_id
            and row["numeric_value"] is not None
        ]
        for data_row, row in enumerate(variable_values, start=1):
            chart_data.write_datetime(
                data_row,
                date_column,
                _excel_datetime(row["observed_at"]),
                date_format,
            )
            chart_data.write_number(
                data_row, value_column, float(row["numeric_value"]), number
            )

    charts = workbook.add_worksheet("Graficas")
    charts.write("A1", f"Gráficas de telemetría - {station_name}", title)
    charts.write(
        "A2",
        "Gráficas nativas de Excel con fechas y textos en español (hora de Uruguay).",
        subtitle,
    )
    charts.hide_gridlines(2)
    charts.set_column("A:A", 2)
    charts.set_column("B:N", 13)
    chart_row = 3
    wide_last_row = len(by_time) + 2
    note_row = 3
    for series_index, variable_id in enumerate(selected_ids):
        variable_values = [
            row
            for row in ordered_rows
            if int(row["variable_id"]) == variable_id
            and row["numeric_value"] is not None
        ]
        if wide_last_row < 3 or len(variable_values) < 2:
            variable_name = variable_map[variable_id]["name"]
            charts.write(
                note_row,
                1,
                f"Sin gráfica para {variable_name}: "
                "no hay al menos dos valores numéricos.",
                subtitle,
            )
            note_row += 1
            continue
        numeric_values = [float(row["numeric_value"]) for row in variable_values]
        timestamps = [row["observed_at"] for row in variable_values]
        axis_minimum, axis_maximum = _axis_bounds(numeric_values)
        interval_days = _date_axis_interval_days(timestamps)
        date_column = series_index * 2
        value_column = date_column + 1
        last_series_row = len(variable_values)
        chart = workbook.add_chart({"type": "scatter", "subtype": "straight"})
        chart.add_series(
            {
                "name": variable_map[variable_id]["name"],
                "categories": [
                    "Series Graficas",
                    1,
                    date_column,
                    last_series_row,
                    date_column,
                ],
                "values": [
                    "Series Graficas",
                    1,
                    value_column,
                    last_series_row,
                    value_column,
                ],
                "line": {"color": "#2F75B5", "width": 2.25},
                "marker": {"type": "none"},
            }
        )
        unit = variable_map[variable_id].get("unit") or ""
        chart.set_title(
            {"name": f"{variable_map[variable_id]['name']} — {station_name}"}
        )
        chart.set_x_axis(
            {
                "name": "Fecha y hora (Uruguay)",
                "num_format": "dd/mm/yyyy hh:mm",
                "major_unit": interval_days,
                "label_position": "low",
                "num_font": {"rotation": -45, "size": 9},
            }
        )
        chart.set_y_axis(
            {
                "name": unit or "Valor",
                "min": axis_minimum,
                "max": axis_maximum,
                "num_format": "0.00",
                "major_gridlines": {"visible": True, "line": {"color": "#D9E2F3"}},
            }
        )
        chart.set_legend({"none": True})
        chart.set_plotarea({"fill": {"color": "#FFFFFF"}, "border": {"none": True}})
        chart.set_chartarea(
            {"fill": {"color": "#FFFFFF"}, "border": {"color": "#D9E2F3"}}
        )
        chart.show_blanks_as("span")
        chart.set_size({"width": 900, "height": 420})
        charts.insert_chart(chart_row, 1, chart)
        chart_row += 22

    workbook.close()
    return output.getvalue()
