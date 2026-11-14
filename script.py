#!/usr/bin/env python3
"""
INUMET - Carrasco Telemetry Collector
=====================================

Descarga el dataset público de INUMET, filtra únicamente la estación:
    Carrasco - Aeropuerto Internacional Gral. Cesáreo L. Berisso
    idStr: CARRASCO
    código OMM: 86580
    OACI: SUMU

Genera, por cada ejecución:
    output/YYYY-MM-DD_HH-MM-SS/
        carrasco_YYYY-MM-DD_HH-MM-SS.json
        carrasco_YYYY-MM-DD_HH-MM-SS.xlsx
        graficas/
            temperatura_punto_rocio.png
            humedad_relativa.png
            presion_atmosferica.png
            viento_rafagas.png
            visibilidad.png
            ... otras variables numéricas disponibles

El Excel incluye:
    - Telemetria Carrasco
    - Graficas
    - Resumen
    - Estacion y Variables

Uso:
    python script.py

Opcional:
    python script.py --output ./mis_datos
    python script.py --timeout 60
    python script.py --no-show

Requiere Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

INUMET_URL = (
    "https://www.inumet.gub.uy/reportes/estadoActual/datos_inumet_ui_publica.mch"
)

# Identificadores conocidos y estables de Carrasco.
CARRASCO_ID_STR = "CARRASCO"
CARRASCO_OMM = "86580"
CARRASCO_OACI = "SUMU"

# Variables principales que aparecían en la planilla anterior.
VAR_IDS = {
    "direccion_viento": 8,
    "humedad_relativa": 25,
    "rafaga": 28,
    "viento": 29,
    "presion_nivel_mar": 45,
    "precipitacion_24h": 46,
    "temperatura": 47,
    "punto_rocio": 59,
    "visibilidad": 74,
    "precipitacion_horaria": 94,
    "viento_maximo_horario": 105,
}

# Nombres cortos para columnas principales.
DISPLAY_NAMES = {
    8: "Dirección viento",
    25: "Humedad relativa",
    28: "Ráfaga",
    29: "Viento",
    45: "Presión nivel mar",
    46: "Precipitación 24 h",
    47: "Temperatura",
    59: "Punto de rocío",
    74: "Visibilidad",
    94: "Precipitación horaria",
    105: "Viento máximo horario",
}

# Alias usados para localizar series incluso si cambia levemente el nombre humano.
CHART_GROUPS = [
    {
        "filename": "temperatura_punto_rocio.png",
        "title": "Temperatura y punto de rocío - Carrasco",
        "ids": [47, 59],
        "ylabel": "Temperatura (°C)",
    },
    {
        "filename": "humedad_relativa.png",
        "title": "Humedad relativa - Carrasco",
        "ids": [25],
        "ylabel": "Humedad relativa (%)",
    },
    {
        "filename": "presion_atmosferica.png",
        "title": "Presión atmosférica a nivel del mar - Carrasco",
        "ids": [45],
        "ylabel": "Presión (hPa)",
    },
    {
        "filename": "viento_rafagas.png",
        "title": "Viento y ráfagas - Carrasco",
        "ids": [29, 28, 105],
        "ylabel": "Velocidad",
    },
    {
        "filename": "visibilidad.png",
        "title": "Visibilidad - Carrasco",
        "ids": [74],
        "ylabel": "Visibilidad (km)",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga y procesa telemetría pública de INUMET para Carrasco."
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Directorio base de salida. Por defecto: ./output",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout HTTP en segundos. Por defecto: 30",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="No abrir automáticamente el Excel al terminar.",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout debe ser mayor que cero")
    return args


def download_json(timeout: int) -> dict[str, Any]:
    """Descarga y valida el dataset público de INUMET."""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "INUMET-Carrasco-Collector/1.0",
        "Cache-Control": "no-cache",
    }

    response = requests.get(INUMET_URL, headers=headers, timeout=timeout)
    response.raise_for_status()

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RuntimeError(
            "INUMET respondió, pero el contenido no pudo interpretarse como JSON."
        ) from exc

    required = {"estaciones", "variables", "fechas", "observaciones"}
    missing = required.difference(data.keys())
    if missing:
        raise RuntimeError(
            f"El JSON de INUMET cambió de estructura. Faltan claves: {sorted(missing)}"
        )

    return data


def find_carrasco_station(
    estaciones: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """
    Encuentra Carrasco usando identificadores estables.

    Prioridad:
      1. idStr=CARRASCO
      2. codigoOMM=86580
      3. idOACI=SUMU
      4. nombre/displayName contiene Carrasco
    """
    checks = [
        lambda s: str(s.get("idStr", "")).upper() == CARRASCO_ID_STR,
        lambda s: str(s.get("codigoOMM", "")).lstrip("_") == CARRASCO_OMM,
        lambda s: str(s.get("idOACI", "")).upper() == CARRASCO_OACI,
        lambda s: (
            "carrasco" in str(s.get("nombre") or s.get("displayName") or "").lower()
        ),
    ]

    for check in checks:
        for index, station in enumerate(estaciones):
            if check(station):
                return index, station

    raise RuntimeError(
        "No se encontró la estación de Carrasco en el JSON recibido de INUMET."
    )


def parse_datetime(value: Any) -> pd.Timestamp:
    """
    Convierte las fechas de INUMET de forma tolerante.

    INUMET puede devolver ISO-8601 u otros textos que pandas reconoce.
    Se conserva la hora del dato; si tiene zona horaria se elimina la
    información tz para que Excel pueda escribirla correctamente.
    """
    if value is None:
        return pd.NaT

    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT

    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_localize(None)

    return ts


def numeric_or_original(value: Any) -> Any:
    """Convierte strings numéricos a float sin destruir textos como TRAZA/calmo."""
    if value is None:
        return np.nan

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return np.nan
        return value

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in {"", "-", "null", "None"}:
            return np.nan

        # INUMET usa TRAZA para precipitación no medible cuantitativamente.
        if cleaned.upper() == "TRAZA":
            return "TRAZA"

        try:
            return float(cleaned.replace(",", "."))
        except ValueError:
            return cleaned

    return value


def direction_to_cardinal(value: Any) -> str | None:
    """Convierte grados de dirección de viento a 16 puntos cardinales."""
    try:
        deg = float(value) % 360
    except (TypeError, ValueError):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return str(value)

    labels = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    index = int((deg + 11.25) // 22.5) % 16
    return labels[index]


def normalize_carrasco(
    data: dict[str, Any],
    station_index: int,
    station: dict[str, Any],
) -> pd.DataFrame:
    """
    Normaliza la matriz interna de INUMET.

    El frontend utiliza:
        observaciones[indice_variable]["datos"][indice_estacion][indice_fecha_variable]

    y:
        observaciones[indice_variable]["iFechas"]

    para enlazar cada valor con:
        fechas[indice_fecha_global]
    """
    variables = data["variables"]
    observaciones = data["observaciones"]
    fechas = data["fechas"]

    if len(observaciones) != len(variables):
        raise RuntimeError(
            "La cantidad de observaciones no coincide con la cantidad de variables."
        )

    rows: list[dict[str, Any]] = []

    for variable_index, variable in enumerate(variables):
        obs = observaciones[variable_index] or {}
        i_fechas = obs.get("iFechas") or []
        datos = obs.get("datos") or []

        if station_index >= len(datos):
            continue

        station_values = datos[station_index]
        if station_values is None:
            continue

        if not isinstance(station_values, list):
            continue

        max_count = min(len(station_values), len(i_fechas))

        for local_time_index in range(max_count):
            global_time_index = i_fechas[local_time_index]

            if not isinstance(global_time_index, int):
                continue
            if global_time_index < 0 or global_time_index >= len(fechas):
                continue

            raw_value = station_values[local_time_index]
            value = numeric_or_original(raw_value)

            if raw_value is None:
                continue

            fecha = parse_datetime(fechas[global_time_index])
            if pd.isna(fecha):
                continue

            variable_id = variable.get("id")
            rows.append(
                {
                    "FechaHora": fecha,
                    "EstacionID": station.get("id"),
                    "Estacion": station.get("nombre")
                    or station.get("displayName")
                    or "Carrasco",
                    "CodigoOMM": station.get("codigoOMM"),
                    "OACI": station.get("idOACI"),
                    "Latitud": station.get("latitud"),
                    "Longitud": station.get("longitud"),
                    "VariableID": variable_id,
                    "Variable": variable.get("nombre")
                    or variable.get("idStr")
                    or f"Variable {variable_id}",
                    "VariableCorta": DISPLAY_NAMES.get(
                        variable_id,
                        variable.get("nombre")
                        or variable.get("idStr")
                        or str(variable_id),
                    ),
                    "Unidad": variable.get("unidad"),
                    "PeriodicidadID": variable.get("periodicidad"),
                    "Valor": value,
                    "ValorRaw": raw_value,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(
            "Carrasco fue encontrado, pero no se extrajeron observaciones."
        )

    df = df.sort_values(["FechaHora", "VariableID"]).reset_index(drop=True)

    # Columna auxiliar para series numéricas.
    df["ValorNumerico"] = pd.to_numeric(df["Valor"], errors="coerce")

    # Dirección cardinal adicional.
    df["DireccionCardinal"] = None
    mask_dir = df["VariableID"] == VAR_IDS["direccion_viento"]
    df.loc[mask_dir, "DireccionCardinal"] = df.loc[mask_dir, "Valor"].apply(
        direction_to_cardinal
    )

    return df


def build_filtered_json(
    station: dict[str, Any],
    df: pd.DataFrame,
    captured_at: datetime,
) -> dict[str, Any]:
    """Crea un JSON ya filtrado y normalizado exclusivamente para Carrasco."""
    records = []

    for row in df.itertuples(index=False):
        value = row.Valor
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and math.isnan(value):
            value = None

        numeric = row.ValorNumerico
        if isinstance(numeric, np.generic):
            numeric = numeric.item()
        if isinstance(numeric, float) and math.isnan(numeric):
            numeric = None

        records.append(
            {
                "fecha_hora": row.FechaHora.isoformat(),
                "variable_id": int(row.VariableID)
                if pd.notna(row.VariableID)
                else None,
                "variable": row.Variable,
                "unidad": row.Unidad,
                "periodicidad_id": int(row.PeriodicidadID)
                if pd.notna(row.PeriodicidadID)
                else None,
                "valor": value,
                "valor_numerico": numeric,
                "direccion_cardinal": row.DireccionCardinal,
            }
        )

    return {
        "fuente": INUMET_URL,
        "capturado_en": captured_at.isoformat(),
        "estacion": station,
        "cantidad_registros": len(records),
        "telemetria": records,
    }


def make_wide_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produce formato ancho para Excel:
        FechaHora | Temperatura | Humedad | ...
    """
    working = df.copy()
    working = working[pd.notna(working["ValorNumerico"])]

    if working.empty:
        return pd.DataFrame({"FechaHora": sorted(df["FechaHora"].unique())})

    # Evitar duplicados improbables en FechaHora+Variable:
    # si hay varios, conservar el último recibido.
    working = working.sort_values("FechaHora").drop_duplicates(
        ["FechaHora", "VariableCorta"], keep="last"
    )

    wide = working.pivot(
        index="FechaHora",
        columns="VariableCorta",
        values="ValorNumerico",
    ).reset_index()

    wide.columns.name = None
    return wide.sort_values("FechaHora").reset_index(drop=True)


def safe_filename(text: str) -> str:
    text = re.sub(r"[^\w\-]+", "_", text.strip().lower(), flags=re.UNICODE)
    return text.strip("_")[:80] or "grafica"


def save_matplotlib_chart(
    df: pd.DataFrame,
    variable_ids: list[int],
    title: str,
    ylabel: str,
    path: Path,
) -> bool:
    subset = df[
        df["VariableID"].isin(variable_ids) & df["ValorNumerico"].notna()
    ].copy()

    if subset.empty:
        return False

    fig, ax = plt.subplots(figsize=(14, 6))

    plotted = False
    for variable_id in variable_ids:
        series = subset[subset["VariableID"] == variable_id].sort_values("FechaHora")
        if series.empty:
            continue

        label = str(series["VariableCorta"].iloc[0])
        unit = series["Unidad"].dropna()
        if not unit.empty:
            label = f"{label} ({unit.iloc[0]})"

        ax.plot(
            series["FechaHora"],
            series["ValorNumerico"],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=label,
        )
        plotted = True

    if not plotted:
        plt.close(fig)
        return False

    ax.set_title(title)
    ax.set_xlabel("Fecha / hora")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
    fig.autofmt_xdate()

    if len(variable_ids) > 1:
        ax.legend()

    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return True


def generate_png_charts(df: pd.DataFrame, chart_dir: Path) -> list[Path]:
    chart_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    charted_ids: set[int] = set()

    for group in CHART_GROUPS:
        path = chart_dir / group["filename"]
        if save_matplotlib_chart(
            df=df,
            variable_ids=group["ids"],
            title=group["title"],
            ylabel=group["ylabel"],
            path=path,
        ):
            generated.append(path)
            charted_ids.update(group["ids"])

    # Gráficas individuales para el resto de variables numéricas.
    numeric = df[df["ValorNumerico"].notna()]
    for variable_id in sorted(numeric["VariableID"].dropna().unique()):
        variable_id = int(variable_id)
        if variable_id in charted_ids:
            continue

        series = numeric[numeric["VariableID"] == variable_id]
        if series.empty:
            continue

        variable_name = str(series["VariableCorta"].iloc[0])
        unit_series = series["Unidad"].dropna()
        unit = str(unit_series.iloc[0]) if not unit_series.empty else ""

        path = chart_dir / f"{safe_filename(variable_name)}.png"
        ylabel = f"{variable_name} ({unit})" if unit else variable_name

        if save_matplotlib_chart(
            df=df,
            variable_ids=[variable_id],
            title=f"{variable_name} - Carrasco",
            ylabel=ylabel,
            path=path,
        ):
            generated.append(path)

    return generated


def write_excel(
    df: pd.DataFrame,
    wide: pd.DataFrame,
    station: dict[str, Any],
    variables: list[dict[str, Any]],
    xlsx_path: Path,
    chart_paths: list[Path],
    captured_at: datetime,
) -> None:
    """
    Genera un Excel compatible con Microsoft Excel usando pandas + XlsxWriter.
    """
    main_columns = [
        "FechaHora",
        "VariableID",
        "Variable",
        "Unidad",
        "Valor",
        "ValorNumerico",
        "DireccionCardinal",
        "PeriodicidadID",
    ]

    telemetria = df[main_columns].copy()

    # Resumen por variable.
    numeric = df[df["ValorNumerico"].notna()].copy()
    if not numeric.empty:
        resumen = numeric.groupby(
            ["VariableID", "Variable", "Unidad"],
            dropna=False,
            as_index=False,
        ).agg(
            Registros=("ValorNumerico", "count"),
            Minimo=("ValorNumerico", "min"),
            Maximo=("ValorNumerico", "max"),
            Promedio=("ValorNumerico", "mean"),
            Ultimo=("ValorNumerico", "last"),
            PrimeraFecha=("FechaHora", "min"),
            UltimaFecha=("FechaHora", "max"),
        )
    else:
        resumen = pd.DataFrame(
            columns=[
                "VariableID",
                "Variable",
                "Unidad",
                "Registros",
                "Minimo",
                "Maximo",
                "Promedio",
                "Ultimo",
                "PrimeraFecha",
                "UltimaFecha",
            ]
        )

    # Metadatos de la estación.
    estacion_rows = [
        ("Capturado en", captured_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")),
        ("Fuente", INUMET_URL),
        ("ID", station.get("id")),
        ("idStr", station.get("idStr")),
        ("Nombre", station.get("nombre")),
        ("Nombre público", station.get("displayNamePublic")),
        ("Código OMM", station.get("codigoOMM")),
        ("Código pluviométrico", station.get("codigoPluviometrico")),
        ("OACI", station.get("idOACI")),
        ("Latitud", station.get("latitud")),
        ("Longitud", station.get("longitud")),
        ("Altitud", station.get("altitud")),
        ("Cota barométrica", station.get("cotaBarom")),
        ("Automática", station.get("tipoAutomatica")),
        ("Aeronáutica", station.get("tipoAeronautica")),
        ("Huso horario", station.get("husoHorario")),
        ("Gerencia", station.get("gerencia")),
        ("Estado", station.get("estado")),
    ]
    station_df = pd.DataFrame(estacion_rows, columns=["Campo", "Valor"])

    variable_ids_present = set(df["VariableID"].dropna().astype(int))
    variables_df = pd.DataFrame(
        [
            {
                "ID": var.get("id"),
                "ID String": var.get("idStr"),
                "Nombre": var.get("nombre"),
                "Unidad": var.get("unidad"),
                "Periodicidad": var.get("periodicidad"),
                "Tipo medición": var.get("tipoDeMedicion"),
                "Grupo": var.get("grupoVista"),
                "Descripción": var.get("descripVariab"),
                "Período de registro": var.get("periodoDeRegistro"),
            }
            for var in variables
            if var.get("id") in variable_ids_present
        ]
    )

    with pd.ExcelWriter(
        xlsx_path,
        engine="xlsxwriter",
        datetime_format="dd/mm/yyyy hh:mm",
        date_format="dd/mm/yyyy",
    ) as writer:
        telemetria.to_excel(
            writer,
            sheet_name="Telemetria Carrasco",
            index=False,
            startrow=2,
        )
        wide.to_excel(
            writer,
            sheet_name="Datos por Hora",
            index=False,
            startrow=2,
        )
        resumen.to_excel(
            writer,
            sheet_name="Resumen",
            index=False,
            startrow=4,
        )
        station_df.to_excel(
            writer,
            sheet_name="Estacion y Variables",
            index=False,
            startrow=2,
        )
        variables_df.to_excel(
            writer,
            sheet_name="Estacion y Variables",
            index=False,
            startrow=len(station_df) + 6,
        )

        workbook = writer.book

        # Formatos.
        title_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 16,
                "align": "left",
                "valign": "vcenter",
            }
        )
        subtitle_fmt = workbook.add_format(
            {
                "italic": True,
                "font_size": 10,
            }
        )
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm"})
        number_fmt = workbook.add_format({"num_format": "0.00"})
        integer_fmt = workbook.add_format({"num_format": "0"})
        wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})

        # Hoja Telemetría.
        ws = writer.sheets["Telemetria Carrasco"]
        ws.write("A1", "Telemetría INUMET - Carrasco", title_fmt)
        ws.write(
            "A2",
            f"Generado: {captured_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}",
            subtitle_fmt,
        )
        ws.freeze_panes(3, 1)
        ws.autofilter(
            2,
            0,
            2 + len(telemetria),
            max(0, len(telemetria.columns) - 1),
        )
        ws.set_column("A:A", 19, date_fmt)
        ws.set_column("B:B", 11, integer_fmt)
        ws.set_column("C:C", 34)
        ws.set_column("D:D", 13)
        ws.set_column("E:F", 15, number_fmt)
        ws.set_column("G:G", 18)
        ws.set_column("H:H", 14, integer_fmt)

        for col_num, value in enumerate(telemetria.columns):
            ws.write(2, col_num, value, header_fmt)

        # Hoja formato ancho.
        ws_wide = writer.sheets["Datos por Hora"]
        ws_wide.write("A1", "Datos de Carrasco por fecha/hora", title_fmt)
        ws_wide.write(
            "A2",
            "Formato ancho para análisis, Power BI y creación de nuevas gráficas.",
            subtitle_fmt,
        )
        ws_wide.freeze_panes(3, 1)
        ws_wide.set_column("A:A", 19, date_fmt)
        if len(wide.columns) > 1:
            ws_wide.set_column(1, len(wide.columns) - 1, 20, number_fmt)
        for col_num, value in enumerate(wide.columns):
            ws_wide.write(2, col_num, value, header_fmt)

        if len(wide) > 0:
            ws_wide.autofilter(
                2,
                0,
                2 + len(wide),
                max(0, len(wide.columns) - 1),
            )

        # Resumen.
        ws_summary = writer.sheets["Resumen"]
        ws_summary.write("A1", "Resumen - Carrasco", title_fmt)
        ws_summary.write("A2", station.get("nombre", "Carrasco"), subtitle_fmt)
        ws_summary.write(
            "A3",
            f"Registros normalizados: {len(df)} | "
            f"Desde: {df['FechaHora'].min()} | Hasta: {df['FechaHora'].max()}",
            subtitle_fmt,
        )
        ws_summary.freeze_panes(5, 0)
        ws_summary.set_column("A:A", 11)
        ws_summary.set_column("B:B", 34)
        ws_summary.set_column("C:C", 13)
        ws_summary.set_column("D:H", 13, number_fmt)
        ws_summary.set_column("I:J", 19, date_fmt)
        for col_num, value in enumerate(resumen.columns):
            ws_summary.write(4, col_num, value, header_fmt)

        # Estación y Variables.
        ws_meta = writer.sheets["Estacion y Variables"]
        ws_meta.write("A1", "Estación Carrasco", title_fmt)
        ws_meta.set_column("A:A", 24)
        ws_meta.set_column("B:B", 60, wrap_fmt)
        ws_meta.set_column("C:I", 22, wrap_fmt)

        station_header_row = 2
        for col_num, value in enumerate(station_df.columns):
            ws_meta.write(station_header_row, col_num, value, header_fmt)

        vars_header_row = len(station_df) + 6
        ws_meta.write(
            vars_header_row - 2,
            0,
            "Variables disponibles para Carrasco",
            title_fmt,
        )
        for col_num, value in enumerate(variables_df.columns):
            ws_meta.write(vars_header_row, col_num, value, header_fmt)

        # Hoja de gráficas con imágenes generadas por matplotlib.
        ws_charts = workbook.add_worksheet("Graficas")
        ws_charts.write("A1", "Gráficas de telemetría - Carrasco", title_fmt)
        ws_charts.write(
            "A2",
            "Las imágenes también se guardan como PNG junto al Excel.",
            subtitle_fmt,
        )
        ws_charts.set_column("A:A", 2)
        ws_charts.set_column("B:N", 13)

        row = 3
        for chart_path in chart_paths:
            try:
                ws_charts.insert_image(
                    row,
                    1,
                    str(chart_path),
                    {"x_scale": 0.72, "y_scale": 0.72},
                )
                row += 23
            except Exception:
                # Si una imagen falla, el Excel sigue generándose.
                continue

        # Además, crear gráficos nativos de Excel para los grupos principales.
        # Así, si el usuario modifica datos dentro de "Datos por Hora",
        # las gráficas nativas podrán actualizarse en Excel.
        if not wide.empty and "FechaHora" in wide.columns:
            col_map = {name: i for i, name in enumerate(wide.columns)}
            excel_chart_row = row + 2

            for group in CHART_GROUPS:
                available = []
                for vid in group["ids"]:
                    col_name = None
                    matches = df[df["VariableID"] == vid]
                    if not matches.empty:
                        col_name = str(matches["VariableCorta"].iloc[0])
                    if col_name in col_map:
                        available.append((vid, col_name))

                if not available:
                    continue

                chart = workbook.add_chart({"type": "line"})
                for _, col_name in available:
                    col_idx = col_map[col_name]
                    chart.add_series(
                        {
                            "name": ["Datos por Hora", 2, col_idx],
                            "categories": [
                                "Datos por Hora",
                                3,
                                0,
                                2 + len(wide),
                                0,
                            ],
                            "values": [
                                "Datos por Hora",
                                3,
                                col_idx,
                                2 + len(wide),
                                col_idx,
                            ],
                            "line": {"width": 1.5},
                        }
                    )

                chart.set_title({"name": group["title"]})
                chart.set_x_axis(
                    {
                        "name": "Fecha / hora",
                        "date_axis": True,
                        "num_format": "dd/mm hh:mm",
                        "label_position": "low",
                    }
                )
                chart.set_y_axis({"name": group["ylabel"]})
                chart.set_legend({"position": "bottom"})
                chart.set_size({"width": 900, "height": 420})
                ws_charts.insert_chart(excel_chart_row, 1, chart)
                excel_chart_row += 22


def open_file(path: Path) -> None:
    """Abre el Excel con la aplicación predeterminada en Windows/Linux/macOS."""
    try:
        if sys.platform.startswith("win"):
            import os

            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(path)])
        else:
            import subprocess

            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        # Abrir el archivo es una comodidad, no debe hacer fallar el proceso.
        pass


def main() -> int:
    args = parse_args()
    capture_time = datetime.now(timezone.utc).astimezone()
    timestamp = capture_time.strftime("%Y-%m-%d_%H-%M-%S")

    base_dir = Path(args.output).expanduser().resolve()
    run_dir = base_dir / timestamp
    chart_dir = run_dir / "graficas"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("[1/6] Descargando JSON de INUMET...")
    data = download_json(args.timeout)

    print("[2/6] Localizando estación Carrasco...")
    station_index, station = find_carrasco_station(data["estaciones"])
    print(
        f"      Encontrada: {station.get('nombre')} "
        f"(OMM {station.get('codigoOMM')}, OACI {station.get('idOACI')})"
    )

    print("[3/6] Normalizando telemetría de Carrasco...")
    df = normalize_carrasco(data, station_index, station)
    wide = make_wide_dataframe(df)

    print("[4/6] Guardando JSON filtrado...")
    filtered = build_filtered_json(station, df, capture_time)
    json_path = run_dir / f"carrasco_{timestamp}.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(filtered, fh, ensure_ascii=False, indent=2)

    print("[5/6] Generando gráficas PNG...")
    chart_paths = generate_png_charts(df, chart_dir)

    print("[6/6] Generando Excel...")
    xlsx_path = run_dir / f"carrasco_{timestamp}.xlsx"
    write_excel(
        df=df,
        wide=wide,
        station=station,
        variables=data["variables"],
        xlsx_path=xlsx_path,
        chart_paths=chart_paths,
        captured_at=capture_time,
    )

    print()
    print("=" * 72)
    print("PROCESO COMPLETADO")
    print("=" * 72)
    print(f"Estación       : {station.get('nombre')}")
    print(f"Registros      : {len(df)}")
    print(f"Variables      : {df['VariableID'].nunique()}")
    print(f"Primera fecha  : {df['FechaHora'].min()}")
    print(f"Última fecha   : {df['FechaHora'].max()}")
    print(f"JSON filtrado  : {json_path}")
    print(f"Excel          : {xlsx_path}")
    print(f"Gráficas       : {chart_dir}")
    print("=" * 72)

    if not args.no_show:
        open_file(xlsx_path)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"\nERROR HTTP: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
