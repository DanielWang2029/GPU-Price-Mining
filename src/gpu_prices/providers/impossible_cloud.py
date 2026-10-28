from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.impossiblecloud.com/baremetal"
REGIONS = {"US": "North America", "EU": "Europe", "APAC": "Asia"}


def parse_offers(html: str) -> dict[str, dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    selected: dict[str, dict[str, object]] = {}
    for card in soup.select(".baremetal-gpu-item"):
        model_node = card.select_one('[fs-cmsfilter-field="GPU"]')
        capacity = card.select_one(".gpu-info-wrapper.first-row .gpu-nodes-wrapper")
        if model_node is None or capacity is None:
            continue
        model = text(model_node)
        if model in selected or "By Request" in text(capacity):
            continue
        region_raw = text(card.select_one('[fs-cmsfilter-field="location"]'))
        term_raw = text(card.select_one('[fs-cmsfilter-field="Duration"]'))
        price_raw = text(card.select_one('[fs-list-field="price"]'))
        if not region_raw or not term_raw or not price_raw:
            continue
        selected[model] = {
            "price": money_2(parse_price(price_raw)),
            "raw_price": price_raw,
            "region": REGIONS.get(region_raw, region_raw),
            "term": int(parse_price(term_raw)),
            "capacity": text(capacity),
        }
    return selected


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    offers = parse_offers(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        offer = offers.get(row.gpu_model_code)
        if offer is None:
            raise ValueError(
                f"Impossible Cloud omitted eligible {row.gpu_model_code} offer"
            )
        if offer["region"] != row.region:
            raise ValueError(
                f"Impossible Cloud {row.gpu_model_code} region changed from "
                f"{row.region} to {offer['region']}"
            )
        if row.term is None or offer["term"] != int(row.term):
            raise ValueError(
                f"Impossible Cloud {row.gpu_model_code} term changed from "
                f"{row.term} to {offer['term']}"
            )
        observations.append(
            ok(
                row,
                offer["price"],
                fetched_at=now,
                source_url=URL,
                raw_value=str(offer["raw_price"]),
                note=(
                    "First page-order offer whose GPU capacity is numeric; "
                    f"{offer['capacity']}, {offer['region']}, {offer['term']} months."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Impossible Cloud")
