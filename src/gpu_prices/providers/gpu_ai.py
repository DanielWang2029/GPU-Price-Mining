from __future__ import annotations

from datetime import datetime

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import run_provider_cli

URL = "https://gpu.ai/api/v1/gpu/catalog"
MODELS = {
    "B300": "b300",
    "B200": "b200",
    "H200": "h200_sxm",
    "A100": "a100_80gb",
}


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    catalog = client.get_json(URL).get("gpus", [])
    observations: list[Observation] = []
    for row in rows:
        gpu_type = MODELS[row.gpu_model_code]
        offers = [
            item
            for item in catalog
            if item.get("gpu_model") == gpu_type
            and item.get("community") is False
            and int(item.get("total_available") or 0) > 0
        ]
        if not offers:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=f"GPU.ai has no available secure on-demand {gpu_type} offer.",
                )
            )
            continue
        selected = min(offers, key=lambda item: item["price_per_hour"])
        value = selected["price_per_hour"]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=str(value),
                note=(
                    "Lowest available secure on-demand price in the public GPU.ai "
                    "pricing-page catalog; USD per GPU-hour."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Gpu.ai")
