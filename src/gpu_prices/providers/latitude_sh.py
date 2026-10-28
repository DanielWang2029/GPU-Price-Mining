from __future__ import annotations

import html as html_module
import json
from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://www.latitude.sh/pricing"
PLAN_SLUG = "g4-b300-large"


def parse_plan(html: str) -> dict[str, object]:
    normalized = html_module.unescape(html).replace(r"\"", '"')
    marker = '"plansData":'
    start = normalized.find(marker)
    if start < 0:
        raise ValueError("Latitude plansData payload was not found")
    payload, _ = json.JSONDecoder().raw_decode(normalized[start + len(marker) :])
    return next(
        plan["attributes"]
        for plan in payload["servers"]
        if plan["attributes"]["slug"] == PLAN_SLUG
    )


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    plan = parse_plan(client.get_text(URL))
    gpu_count = int(plan["specs"]["gpu"]["count"])
    us_region = next(
        region for region in plan["regions"] if region["name"] == "United States"
    )
    prices = us_region["pricing"]["USD"]
    rates = {
        1: Decimal(str(prices["month"])) / Decimal(730 * gpu_count),
        12: Decimal(str(prices["year"])) / Decimal(12 * 730 * gpu_count),
    }
    observations: list[Observation] = []
    for row in rows:
        if row.term is None or int(row.term) not in rates:
            raise ValueError(f"Unsupported Latitude term {row.term}")
        term = int(row.term)
        source_price = prices["month"] if term == 1 else prices["year"]
        observations.append(
            ok(
                row,
                money_2(rates[term]),
                fetched_at=now,
                source_url=URL,
                raw_value=f"{source_price} / {gpu_count} GPU",
                note=(
                    "US node price normalized by 730 hours/month and eight GPUs. "
                    "Workbook term 1 maps Monthly; term 12 maps Paid yearly."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Latitude.sh")
