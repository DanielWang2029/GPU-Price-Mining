from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.civo.com/pricing"
CAPTIONS = {
    "H200": "NVIDIA H200 SXM GPU pricing",
    "B200": "NVIDIA B200 GPU pricing",
    "B300": "NVIDIA B300 GPU pricing",
}


def parse_prices(html: str) -> dict[tuple[str, str], tuple[Decimal, str, int]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[tuple[str, str], tuple[Decimal, str, int]] = {}
    for model, caption_text in CAPTIONS.items():
        caption = next(
            (node for node in soup.find_all("caption") if text(node) == caption_text),
            None,
        )
        if caption is None:
            raise ValueError(f"Civo omitted {caption_text}")
        row = caption.parent.select_one("tbody tr")
        if row is None:
            raise ValueError(f"Civo {model} table had no price row")
        size = text(row.find("td"))
        count_match = re.search(r"(\d+)\s*x\s*NVIDIA", size, re.IGNORECASE)
        if count_match is None:
            raise ValueError(f"Civo {model} GPU count was not found")
        gpu_count = int(count_match.group(1))

        on_demand = row.select_one(
            "td.on-demand-pricing .price-value[data-option='hourly']"
        )
        if on_demand is not None and "N/A" not in text(on_demand):
            raw = text(on_demand)
            result[(model, "On-Demand")] = (
                parse_price(raw) / Decimal(gpu_count),
                raw,
                gpu_count,
            )
        reserved = row.find(id="36_months")
        if reserved is not None:
            price_node = reserved.select_one(".price-value[data-option='hourly']")
            if price_node is not None and "N/A" not in text(price_node):
                raw = text(price_node)
                result[(model, "Reserve")] = (
                    parse_price(raw) / Decimal(gpu_count),
                    raw,
                    gpu_count,
                )
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_prices(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        if row.price_type == "Reserve" and row.term != 36:
            raise ValueError(f"Civo reserve term must be 36, got {row.term}")
        value, raw, gpu_count = prices[(row.gpu_model_code, row.price_type)]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=f"{raw} / {gpu_count} GPU",
                note="Published node price normalized to USD per GPU-hour.",
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Civo")
