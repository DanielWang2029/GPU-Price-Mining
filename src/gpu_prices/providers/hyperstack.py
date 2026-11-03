from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.hyperstack.cloud/gpu-pricing"
STOCK_URL = "https://gpu-stock.hyperstack-docs.workers.dev"
MODEL_LABELS = {
    "B300": "NVIDIA B300",
    "B200": "NVIDIA B200",
    "H200": "NVIDIA H200 SXM",
}
STOCK_MODELS = {
    "B300": "B300-SXM",
    "B200": "B200-SXM",
    "H200": "H200-141G-SXM5",
}


def parse_prices(html: str) -> dict[tuple[str, str], tuple[Decimal, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[tuple[str, str], tuple[Decimal, str]] = {}
    cards = {
        text(card.select_one("h3")): card
        for card in soup.select("#cloud-pricing .page-price_card")
    }
    mappings = {
        "On-Demand": ("On-Demand GPU Pricing", 4),
        "Reserve": ("Reservation Pricing", 1),
    }
    for price_type, (card_name, price_index) in mappings.items():
        card = cards.get(card_name)
        if card is None:
            raise ValueError(f"Hyperstack omitted {card_name}")
        for row in card.select(".page-price_card_row_item"):
            cells = [text(node) for node in row.select("span")]
            if len(cells) <= price_index:
                continue
            for model, label in MODEL_LABELS.items():
                if cells[0] == label:
                    result[(model, price_type)] = (
                        parse_price(cells[price_index]),
                        cells[price_index],
                    )
    return result


def parse_stock(payload: dict[str, object]) -> dict[str, bool]:
    canada = next(item for item in payload["stocks"] if item["region"] == "CANADA-1")
    by_model = {item["model"]: item for item in canada["models"]}
    return {
        model: int(by_model[stock_model]["available"]) > 0
        for model, stock_model in STOCK_MODELS.items()
    }


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_prices(client.get_text(URL))
    stock = parse_stock(client.get_json(STOCK_URL))
    observations: list[Observation] = []
    for row in rows:
        value, raw = prices[(row.gpu_model_code, row.price_type)]
        availability = (
            "AVAILABLE"
            if row.price_type == "Reserve" or stock[row.gpu_model_code]
            else "UNAVAILABLE"
        )
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_price=value,
                gpu_count=1,
                availability=availability,
                raw_value=raw,
                note=(
                    "Published per-GPU quote. On-demand availability uses the "
                    "official live stock mirror; reservation quotes are requestable."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Hyperstack")
