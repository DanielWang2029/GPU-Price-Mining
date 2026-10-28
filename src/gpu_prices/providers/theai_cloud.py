from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://cloud.theai.com/api/v1/pricing"


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(URL)
    if payload.get("currency") != "USD" or payload.get("unit") != "per_gpu_hour":
        raise ValueError("TheAI pricing unit or currency changed")
    offerings = {
        str(item["gpu"]).removeprefix("NVIDIA "): item
        for item in payload.get("offerings", [])
    }
    observations: list[Observation] = []
    for row in rows:
        offering = offerings.get(row.gpu_model_code)
        if offering is None:
            raise ValueError(f"TheAI API omitted {row.gpu_model_code}")
        rates = {
            int(rate["term_months"]): Decimal(str(rate["price"]))
            for rate in offering.get("prices", {}).get("reserved", [])
        }
        if row.term is None or int(row.term) not in rates:
            raise ValueError(f"TheAI omitted {row.gpu_model_code} term {row.term}")
        term = int(row.term)
        observations.append(
            ok(
                row,
                rates[term],
                fetched_at=now,
                source_url=URL,
                effective_at=payload.get("updated_at", ""),
                raw_value=str(rates[term]),
                note=(
                    "Public USD/GPU-hour pricing API. Workbook H200 labels were "
                    "normalized to B300 because both screenshots and the supplier "
                    "API identify the offering as B300."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("TheAI Cloud")
