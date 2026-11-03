from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import run_provider_cli

URL = "https://cloud.theai.com/api/v1/pricing"


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(URL)
    if payload.get("currency") != "USD" or payload.get("unit") != "per_gpu_hour":
        raise ValueError("TheAI pricing unit or currency changed")
    offerings: dict[str, list[dict[str, object]]] = {}
    for item in payload.get("offerings", []):
        model = str(item["gpu"]).removeprefix("NVIDIA ")
        offerings.setdefault(model, []).append(item)
    observations: list[Observation] = []
    for row in rows:
        if row.term is None:
            raise ValueError(f"TheAI term is blank for {row.gpu_model_code}")
        term = int(row.term)
        candidates: list[tuple[dict[str, object], Decimal]] = []
        for offering in offerings.get(row.gpu_model_code, []):
            rates = {
                int(rate["term_months"]): Decimal(str(rate["price"]))
                for rate in offering.get("prices", {}).get("reserved", [])
            }
            if term in rates:
                candidates.append((offering, rates[term]))
        if not candidates:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=(
                        f"TheAI currently publishes no {row.gpu_model_code} "
                        f"{term}-month offering."
                    ),
                )
            )
            continue
        offering, price = next(
            (
                candidate
                for candidate in candidates
                if candidate[0].get("available") is True
            ),
            candidates[0],
        )
        if offering.get("available") is not True:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=(
                        f"TheAI marks its {row.gpu_model_code} {term}-month "
                        "offering unavailable."
                    ),
                )
            )
            continue
        if price is None:
            raise ValueError(f"TheAI API omitted {row.gpu_model_code}")
        observations.append(
            ok(
                row,
                price,
                fetched_at=now,
                source_url=URL,
                effective_at=payload.get("updated_at", ""),
                raw_value=str(price),
                note=(
                    "Public USD/GPU-hour pricing API; selected an available "
                    f"{term}-month {offering.get('location', '')} offering."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("TheAI Cloud")
