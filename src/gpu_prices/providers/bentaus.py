from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli, text

URL = "https://www.bentaus.com/nvidia-b300"
RANGE_RE = re.compile(
    r"\$\s*(?P<low>\d+(?:\.\d+)?)\s*[-–—]\s*\$\s*(?P<high>\d+(?:\.\d+)?)"
)


def parse_ranges(html: str) -> dict[str, tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one("#pricing")
    if section is None:
        raise ValueError("Bentaus pricing section was not found")
    result: dict[str, tuple[str, str]] = {}
    headings = {"On-Demand": "h3", "Reserve": "h5"}
    labels = {"On-Demand": "On-Demand", "Reserve": "Reserved"}
    for price_type, tag in headings.items():
        heading = next(
            (
                node
                for node in section.find_all(tag)
                if text(node) == labels[price_type]
            ),
            None,
        )
        if heading is None:
            raise ValueError(f"Bentaus omitted {labels[price_type]} plan")
        price_heading = heading.find_next("h4")
        match = RANGE_RE.search(text(price_heading))
        if match is None:
            raise ValueError(f"Bentaus omitted {price_type} price range")
        result[price_type] = (match.group("low"), match.group(0))
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    ranges = parse_ranges(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        value, raw = ranges[row.price_type]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note=(
                    "Lower bound of the published indicative USD/GPU-hour range, "
                    "matching the workbook's marked value."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Bentaus")
