from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://deepinfra.com/pricing"


def parse_custom_gpu_table(html: str) -> dict[str, tuple[object, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = next(
        (
            candidate
            for candidate in soup.select("table")
            if [text(cell) for cell in candidate.select("thead th")]
            == ["GPU", "Memory", "Price"]
        ),
        None,
    )
    if table is None:
        raise ValueError("DeepInfra Custom LLM GPU table was not found")
    result: dict[str, tuple[object, str]] = {}
    for row in table.select("tbody tr"):
        cells = [text(cell) for cell in row.find_all("td")]
        if len(cells) != 3 or "GPU-hour" not in cells[2]:
            continue
        result[cells[0]] = (parse_price(cells[2]), cells[2])
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_custom_gpu_table(client.get_text(URL))
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
                    "Custom LLM dedicated deployment price in USD per GPU-hour, "
                    "not a serverless token price."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("DeepInfra")
