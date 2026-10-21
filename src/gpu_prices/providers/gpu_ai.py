from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok, unavailable
from gpu_prices.providers.common import run_provider_cli

URL = "https://api.gpu.ai/v1/pricing"
MODELS = {
    "B300": "b300",
    "B200": "b200",
    "H200": "h200_sxm",
    "A100": "a100_80gb",
}


def fetch_catalog(client: HttpClient) -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    cursor = ""
    while True:
        params: dict[str, object] = {
            "limit": 100,
            "include_unavailable": "true",
        }
        if cursor:
            params["cursor"] = cursor
        payload = client.get_json(URL, params=params)
        catalog.extend(payload.get("data", []))
        cursor = payload.get("next_cursor") or ""
        if not cursor:
            return catalog


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    catalog = fetch_catalog(client)
    observations: list[Observation] = []
    for row in rows:
        gpu_type = MODELS[row.gpu_model_code]
        offers = [
            item
            for item in catalog
            if item.get("gpu_type") == gpu_type
            and item.get("tier") == "on_demand"
            and item.get("community") is False
            and int(item.get("available") or 0) > 0
            and int(item.get("gpu_count") or 0) > 0
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
        per_gpu = [
            (
                Decimal(str(item["price_per_hour"])) / Decimal(str(item["gpu_count"])),
                item,
            )
            for item in offers
        ]
        value, selected = min(per_gpu, key=lambda pair: pair[0])
        observations.append(
            ok(
                row,
                money_2(value),
                fetched_at=now,
                source_url=URL,
                raw_value=(
                    f"{selected['price_per_hour']} / {selected['gpu_count']} GPU"
                ),
                note=(
                    "Lowest available secure on-demand configuration, normalized "
                    "to USD per GPU-hour."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Gpu.ai")
