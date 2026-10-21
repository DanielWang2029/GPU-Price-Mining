from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok, unavailable
from gpu_prices.providers.common import run_provider_cli

URL = "https://app.spheron.ai/api/gpu-offers"
MODELS = {
    "B300": {"B300_SXM6", "B300_SXM6_CC"},
    "B200": {"B200_SXM6"},
    "H200": {"H200_SXM5"},
    "A100": {"A100_80G_SXM4", "A100_80G_PCIE", "A100_80G_NVL"},
}


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(
        URL,
        params={"computeType": "gpu", "page": 1, "limit": 100},
        headers={"Accept": "application/json"},
    )
    if payload.get("totalPages", 1) > 1:
        raise ValueError("Spheron catalog exceeded the requested page size")
    groups = payload.get("data", [])
    observations: list[Observation] = []
    for row in rows:
        instance_type = "DEDICATED" if row.price_type == "On-Demand" else "SPOT"
        offers = [
            offer
            for group in groups
            if group.get("gpuModel") in MODELS[row.gpu_model_code]
            for offer in group.get("offers", [])
            if offer.get("instanceType") == instance_type
            and offer.get("available") is True
            and offer.get("maintenance") is not True
            and int(offer.get("gpuCount") or 0) > 0
        ]
        if not offers:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=(
                        f"Spheron currently has no available {instance_type.lower()} "
                        f"{row.gpu_model_code} offer."
                    ),
                )
            )
            continue
        candidates = []
        for offer in offers:
            raw_price = (
                offer.get("spot_price")
                if instance_type == "SPOT"
                else offer.get("price")
            )
            if raw_price is None:
                continue
            per_gpu = Decimal(str(raw_price)) / Decimal(str(offer["gpuCount"]))
            candidates.append((per_gpu, offer, raw_price))
        if not candidates:
            raise ValueError(
                f"Spheron {row.gpu_model_code} {instance_type} offers had no prices"
            )
        value, selected, raw_price = min(candidates, key=lambda item: item[0])
        observations.append(
            ok(
                row,
                money_2(value),
                fetched_at=now,
                source_url=URL,
                raw_value=f"{raw_price} / {selected['gpuCount']} GPU",
                note=(
                    "Lowest available public offer normalized to USD per GPU-hour; "
                    f"offer {selected.get('offerId', '')}."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Spheron")
