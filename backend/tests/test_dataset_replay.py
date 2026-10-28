import asyncio
from datetime import datetime, timezone

import pandas as pd

from backend.dataset_replay import DatasetReplay


def test_dataset_replay_ingests_current_demo_rows_and_stops(tmp_path):
    dataset = tmp_path / "readings.csv"
    pd.DataFrame([{
        "timestamp": "2020-01-01T00:00:00Z",
        "voltage": 230,
        "current": 2,
        "power": 460,
        "energy": 0.00064,
    }]).to_csv(dataset, index=False)
    captured = []

    async def exercise_replay():
        replay = DatasetReplay(dataset, 60, lambda reading, source: captured.append((reading, source)))
        status = await replay.start()
        assert status["running"]
        await asyncio.sleep(0)
        assert len(captured) == 1
        reading, source = captured[0]
        assert source == "demo"
        assert (datetime.now(timezone.utc) - reading.timestamp).total_seconds() < 5
        assert reading.power == 460
        assert reading.energy == 0.00064
        stopped = await replay.stop()
        assert not stopped["running"]
        assert stopped["rows_processed"] == 1

    asyncio.run(exercise_replay())