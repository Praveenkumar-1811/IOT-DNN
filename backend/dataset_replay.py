import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from backend.preprocessing import clean_dataset
from backend.schemas import ReadingInput

logger = logging.getLogger(__name__)


class DatasetReplay:
    def __init__(self, path: Path, interval_seconds: int, ingest: Callable):
        self.path = path
        self.interval_seconds = interval_seconds
        self.ingest = ingest
        self._rows: list[dict] = []
        self._index = 0
        self._processed = 0
        self._task: asyncio.Task | None = None
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "running": self.running,
            "source": "demo",
            "dataset": self.path.name,
            "interval_seconds": self.interval_seconds,
            "rows_processed": self._processed,
            "dataset_rows": len(self._rows),
            "last_error": self._last_error,
        }

    async def start(self) -> dict:
        if self.running:
            return self.status()
        if not self.path.is_file():
            raise FileNotFoundError(f"Dataset not found: {self.path.name}")
        frame = clean_dataset(pd.read_csv(self.path))
        self._rows = frame.to_dict(orient="records")
        if not self._rows:
            raise ValueError("Dataset contains no valid readings")
        self._last_error = None
        self._task = asyncio.create_task(self._run(), name="dataset-replay")
        return self.status()

    async def stop(self) -> dict:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        return self.status()

    async def _run(self) -> None:
        try:
            while True:
                row = self._rows[self._index]
                self._index = (self._index + 1) % len(self._rows)
                power = float(row["voltage"] * row["current"])
                self.ingest(
                    ReadingInput(
                        timestamp=datetime.now(timezone.utc),
                        voltage=float(row["voltage"]),
                        current=float(row["current"]),
                        power=power,
                        energy=float(row["energy"]),
                    ),
                    source="demo",
                )
                self._processed += 1
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Dataset replay stopped after an ingestion error")