from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://data-api.compute-index.com/public/indices"
PAGE_URL = "https://www.computedesk.com/indexes-overview"
ALIASES = {
    "CDB300": "B300",
    "CDB200": "B200",
    "CDH200": "H200",
}


def parse_indices(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for series in payload.get("indices", []):
        model = ALIASES.get(series.get("alias"))
        if model is not None:
            result[model] = series
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    indices = parse_indices(client.get_json(URL))
    observations: list[Observation] = []
    for row in rows:
        if row.price_type != "Reserve" or row.term != 12:
            raise ValueError(
                f"Compute Desk {row.gpu_model_code} must be 12-month Reserve"
            )
        if row.region != "North America":
            raise ValueError(
                f"Compute Desk {row.gpu_model_code} benchmark must be US/North America"
            )
        series = indices.get(row.gpu_model_code)
        if series is None:
            raise ValueError(f"Compute Desk omitted {row.gpu_model_code}")
        value = Decimal(str(series["latest_value"]))
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_price=value,
                gpu_count=1,
                availability="AVAILABLE",
                effective_at=str(series["latest_date"]),
                raw_value=str(value),
                note=(
                    "Compute Desk US one-year reserved-equivalent index, "
                    "USD per GPU-hour."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Compute Desk")
