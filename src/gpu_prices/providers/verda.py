from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://api.verda.com/v1/instance-types"
SKUS = {
    "GB300": "1GB300.32V",
    "B300": "1B300.30V",
    "B200": "1B200.30V",
    "H200": "1H200.141S.44V",
    "A100": "1A100.22V",
}


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(
        URL, params={"currency": "usd"}, headers={"Accept": "application/json"}
    )
    catalog = {item["instance_type"]: item for item in payload}
    observations: list[Observation] = []
    for row in rows:
        sku = SKUS[row.gpu_model_code]
        item = catalog.get(sku)
        if item is None:
            raise ValueError(f"Verda catalog omitted exact SKU {sku}")
        if item.get("currency", "").lower() != "usd":
            raise ValueError(f"Verda SKU {sku} was not returned in USD")
        field = "price_per_hour" if row.price_type == "On-Demand" else "spot_price"
        raw = item[field]
        gpu_count = int(item["gpu"]["number_of_gpus"])
        if gpu_count < 1:
            raise ValueError(f"Verda SKU {sku} has invalid GPU count {gpu_count}")
        value = Decimal(str(raw)) / Decimal(gpu_count)
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=f"{raw} / {gpu_count} GPU",
                note=(
                    f"Exact public catalog SKU {sku}, normalized to USD per GPU-hour. "
                    "Catalog presence does not guarantee current capacity."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Verda")
