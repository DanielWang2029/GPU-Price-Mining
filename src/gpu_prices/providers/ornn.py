from __future__ import annotations

from datetime import datetime

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://api.ornnai.com/api/daily-index/all"


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(URL, headers={"Accept": "application/json"})
    if not payload.get("success"):
        raise ValueError("Ornn daily-index response was not successful")
    indexes = {item["gpu_type"]: item for item in payload.get("data", [])}
    observations: list[Observation] = []
    for row in rows:
        item = indexes.get(row.gpu_model_code)
        if item is None:
            raise ValueError(f"Ornn response omitted {row.gpu_model_code}")
        observations.append(
            ok(
                row,
                item["index_value"],
                fetched_at=now,
                source_url=URL,
                effective_at=item.get("date", payload.get("date", "")),
                raw_value=str(item["index_value"]),
                note="Settled global daily index in USD per GPU-hour.",
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Ornn")
