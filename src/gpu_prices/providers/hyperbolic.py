from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.hyperbolic.ai/marketplace"


def parse_marketplace(html: str) -> dict[str, tuple[object, str]]:
    soup = BeautifulSoup(html, "html.parser")
    container = next(
        (
            candidate
            for candidate in soup.select("table, div.d-list-wrapper")
            if "Starting From (per GPU hour)" in text(candidate)
        ),
        None,
    )
    if container is None:
        raise ValueError("Hyperbolic marketplace starting-price table was not found")
    result: dict[str, tuple[object, str]] = {}
    if container.name == "table":
        parsed_rows = [
            [text(cell) for cell in row.find_all(["th", "td"])]
            for row in container.select("tr")
        ]
    else:
        parsed_rows = [
            [text(cell) for cell in row.select("p")]
            for row in container.select("div.row.item")
        ]
    for cells in parsed_rows:
        if len(cells) >= 2:
            model = cells[0].removeprefix("Nvidia ").strip()
            try:
                result[model] = (parse_price(cells[1]), cells[1])
            except ValueError:
                continue
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_marketplace(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        value, raw = prices[row.gpu_model_code]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note=(
                    "Advertised marketplace Starting From price in USD per GPU-hour; "
                    "the source says this marketing table refreshes weekly."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Hyperbolic")
