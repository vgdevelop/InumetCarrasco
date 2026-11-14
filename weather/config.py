from __future__ import annotations

import os
from dataclasses import dataclass


def positive_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} debe ser un entero") from exc
    if value < minimum:
        raise RuntimeError(f"{name} debe ser mayor o igual a {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    inumet_url: str
    source_timezone: str
    collect_interval_seconds: int
    request_timeout_seconds: int
    series_max_points: int


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL es obligatoria")
    return Settings(
        database_url=database_url,
        inumet_url=os.getenv(
            "INUMET_URL",
            "https://www.inumet.gub.uy/"
            "reportes/estadoActual/datos_inumet_ui_publica.mch",
        ),
        source_timezone=os.getenv("SOURCE_TIMEZONE", "America/Montevideo"),
        collect_interval_seconds=positive_int(
            "COLLECT_INTERVAL_SECONDS", 300, minimum=60
        ),
        request_timeout_seconds=positive_int("REQUEST_TIMEOUT_SECONDS", 30),
        series_max_points=positive_int("SERIES_MAX_POINTS", 5000, minimum=100),
    )
