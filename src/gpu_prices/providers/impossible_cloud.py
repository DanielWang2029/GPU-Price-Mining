from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.impossiblecloud.com/baremetal"
REGIONS = {"US": "North America", "EU": "Europe", "APAC": "Asia"}


def _parse_offer_cards(html: str) -> dict[str, list[dict[str, object]]]:
    soup = BeautifulSoup(html, "html.parser")
    selected: dict[str, list[dict[str, object]]] = {}
    for card in soup.select(".baremetal-gpu-item"):
        model_node = card.select_one('[fs-cmsfilter-field="GPU"]')
        capacity = card.select_one(".gpu-info-wrapper.first-row .gpu-nodes-wrapper")
        if model_node is None or capacity is None:
            continue
        model = text(model_node)
        if "By Request" in text(capacity):
            continue
        region_raw = text(card.select_one('[fs-cmsfilter-field="location"]'))
        term_raw = text(card.select_one('[fs-cmsfilter-field="Duration"]'))
        price_raw = text(card.select_one('[fs-list-field="price"]'))
        if not region_raw or not term_raw or not price_raw:
            continue
        selected.setdefault(model, []).append(
            {
                "price": money_2(parse_price(price_raw)),
                "raw_price": parse_price(price_raw),
                "raw_value": price_raw,
                "region": REGIONS.get(region_raw, region_raw),
                "term": int(parse_price(term_raw)),
                "capacity": text(capacity),
            }
        )
    return selected


def parse_offers(html: str) -> dict[str, dict[str, object]]:
    return {model: offers[0] for model, offers in _parse_offer_cards(html).items()}


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    offers = _parse_offer_cards(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        if row.term is None:
            raise ValueError(
                f"Impossible Cloud term is blank for {row.gpu_model_code}"
            )
        candidates = [
            offer
            for offer in offers.get(row.gpu_model_code, [])
            if offer["region"] == row.region and offer["term"] == int(row.term)
        ]
        if not candidates:
            raise ValueError(
                f"Impossible Cloud omitted {row.gpu_model_code} in {row.region} "
                f"for {row.term} months"
            )
        offer = candidates[0]
        observations.append(
            ok(
                row,
                offer["price"],
                fetched_at=now,
                source_url=URL,
                raw_price=offer["raw_price"],
                raw_value=str(offer["raw_value"]),
                note=(
                    "First page-order offer whose GPU capacity is numeric; "
                    f"{offer['capacity']}, {offer['region']}, {offer['term']} months."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Impossible Cloud")
