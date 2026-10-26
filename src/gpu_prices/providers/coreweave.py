from __future__ import annotations

from datetime import datetime

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


def parse_prices(html: str) -> dict[str, tuple[object, str]]:
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

    parsed: dict[str, tuple[object, str]] = {}
    for item in table.select('[role="listitem"].kubernetes-gpu-pricing'):
        model = item.select_one("h3.table-model-name[data-product]")
        price = item.select_one(".instance-price .item-value")
        if model is None or price is None or not text(price):
            continue
        parsed[model["data-product"]] = (parse_price(text(price)), text(price))
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
        value, raw = prices[product]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note=(
                    "Published North America on-demand instance-hour price; "
                    "this follows the workbook's red box and is not divided by GPU count."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("CoreWeave")
