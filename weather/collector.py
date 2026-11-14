from __future__ import annotations

import logging
import signal
import time

from weather.config import load_settings
from weather.db import begin_run, finish_run, init_schema, store_dataset
from weather.inumet import fetch_dataset, iter_observations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("tiempo.collector")
RUNNING = True


def request_stop(*_: object) -> None:
    global RUNNING
    RUNNING = False


def collect_once() -> tuple[int, int]:
    settings = load_settings()
    init_schema(settings.database_url)
    run_id = begin_run(settings.database_url)
    try:
        data = fetch_dataset(settings.inumet_url, settings.request_timeout_seconds)
        fetched, inserted = store_dataset(
            settings.database_url,
            data["estaciones"],
            data["variables"],
            iter_observations(data, settings.source_timezone),
        )
        finish_run(settings.database_url, run_id, "success", fetched, inserted)
        LOGGER.info("Recolección correcta: recibidos=%s nuevos=%s", fetched, inserted)
        return fetched, inserted
    except Exception as exc:
        finish_run(settings.database_url, run_id, "failed", error=str(exc))
        LOGGER.exception("Falló la recolección")
        raise


def main() -> None:
    settings = load_settings()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while RUNNING:
        started = time.monotonic()
        try:
            collect_once()
        except Exception:
            pass
        remaining = max(
            1, settings.collect_interval_seconds - (time.monotonic() - started)
        )
        end = time.monotonic() + remaining
        while RUNNING and time.monotonic() < end:
            time.sleep(min(1, end - time.monotonic()))


if __name__ == "__main__":
    main()
