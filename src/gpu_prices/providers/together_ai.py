from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.together.ai/pricing"
MODEL_LABELS = {
    "H200": "NVIDIA HGX H200",
    "B200": "NVIDIA HGX B200",
    "B300": "NVIDIA HGX B300",
}
PRICE_COLUMNS = {"Spot": 1, "On-Demand": 2}
RESERVE_COLUMNS = {1: 3, 3: 4, 6: 5}


def parse_table(html: str) -> dict[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = next(
        (
            candidate
            for candidate in soup.select("table.pricing_table.is-gpu")
            if "91-180 days" in text(candidate.select_one("thead"))
        ),
        None,
    )
    if table is None:
        raise ValueError("Together GPU cluster pricing table was not found")
    result: dict[str, list[str]] = {}
    for row in table.select("tbody tr"):
        cells = [text(cell) for cell in row.find_all("td")]
        if cells:
            result[cells[0]] = cells
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    table = parse_table(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        label = MODEL_LABELS[row.gpu_model_code]
        cells = table.get(label)
        if cells is None:
            raise ValueError(f"Together GPU table omitted {label}")
        if row.price_type == "Reserve":
            if row.term is None or int(row.term) not in RESERVE_COLUMNS:
                raise ValueError(
                    f"Unsupported Together reserve term at row {row.workbook_row}: "
                    f"{row.term}"
                )
            column = RESERVE_COLUMNS[int(row.term)]
        else:
            column = PRICE_COLUMNS[row.price_type]
        raw = cells[column] if column < len(cells) else ""
        try:
            value = parse_price(raw)
        except ValueError:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=f"Together currently publishes {raw or 'no value'} for this tier.",
                )
            )
            continue
        note = "Published GPU cluster price in USD per GPU-hour."
        if row.price_type == "Reserve":
            note += f" Workbook term {row.term} maps to pricing column {column}."
        elif row.price_type == "Spot":
            note += " Together labels this tier Preemptible Compute."
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note=note,
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Together.ai")
