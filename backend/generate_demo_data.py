from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def daily_baseline_current(hour: float) -> float:
    if hour < 5:
        return 1.15 + hour * 0.06
    if hour < 8:
        return 1.45 + (hour - 5) * 0.48
    if hour < 12:
        return 2.89 + (hour - 8) * 0.31
    if hour < 16:
        return 4.13 - (hour - 12) * 0.13
    if hour < 18:
        return 3.61 - (hour - 16) * 0.38
    if hour < 21:
        return 2.85 + (hour - 18) * 0.28
    return 3.69 - (hour - 21) * 0.75


def generate(path: Path | None = None, samples: int = 86_400) -> Path:
    output = path or Path(__file__).parent / "data" / "demo_energy_data.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    start = datetime.now(timezone.utc) - timedelta(seconds=5 * samples)
    rows = []
    for index in range(samples):
        seconds_of_day = (index * 5) % 86_400
        hour = seconds_of_day / 3600
        periodic = 0.10 * np.sin(index * 5 * 0.055) + 0.045 * np.sin(index * 5 * 0.19)
        current = float(np.clip(daily_baseline_current(hour) + periodic + rng.normal(0, 0.10), 0.8, 4.8))
        voltage = float(230 + rng.normal(0, 1.5))
        power = voltage * current
        energy = power * 5 / 3_600_000
        rows.append({
            "timestamp": (start + timedelta(seconds=5 * index)).isoformat(),
            "voltage": voltage,
            "current": current,
            "power": power,
            "energy": energy,
        })
    pd.DataFrame(rows).to_csv(output, index=False)
    print(f"Generated {samples} demo-normal samples at {output}")
    return output


if __name__ == "__main__":
    generate()