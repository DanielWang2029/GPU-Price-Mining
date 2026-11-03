from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.coreweave.com/pricing"
PRODUCTS = {
    "GB200": "nvidia-gb200-nvl72",
    "B200": "nvidia-b200",
    "A100": "nvidia-a100",
}


def parse_prices(html: str) -> dict[str, tuple[Decimal, Decimal, int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    label = next(
        (
            node
            for node in soup.select("strong.eyebrow")
            if text(node).upper() == "REGION: NORTH AMERICA"
        ),
        None,
    )
    if label is None:
        raise ValueError("CoreWeave North America price table was not found")
    table = label.find_next("div", class_="gpu-pricing")
    if table is None:
        raise ValueError("CoreWeave North America GPU rows were not found")

    parsed: dict[str, tuple[Decimal, Decimal, int, str]] = {}
    for item in table.select('[role="listitem"].kubernetes-gpu-pricing'):
        model = item.select_one("h3.table-model-name[data-product]")
        price = item.select_one(".instance-price .item-value")
        if model is None or price is None or not text(price):
            continue
        gpu_count_node = next(
            (
                node.select_one(".table-meta-value")
                for node in item.select(".table-meta-text")
                if "GPU Count" in text(node)
            ),
            None,
        )
        if gpu_count_node is None:
            raise ValueError(f"CoreWeave omitted GPU count for {model['data-product']}")
        gpu_count = int(parse_price(text(gpu_count_node)))
        raw = text(price)
        raw_price = parse_price(raw)
        parsed[model["data-product"]] = (
            raw_price / Decimal(gpu_count),
            raw_price,
            gpu_count,
            raw,
        )
    return parsed


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_prices(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        product = PRODUCTS[row.gpu_model_code]
        if product not in prices:
            raise ValueError(f"CoreWeave North America table omitted {product}")
        value, raw_price, gpu_count, raw = prices[product]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_price=raw_price,
                gpu_count=gpu_count,
                raw_value=raw,
                note=(
                    "Published North America on-demand instance-hour price; "
                    "normalized to the source's single-GPU hourly price."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("CoreWeave")
