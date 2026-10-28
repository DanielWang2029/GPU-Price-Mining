from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import run_provider_cli, text

CAPACITY_URL = "https://aws.amazon.com/ec2/capacityblocks/pricing/"
SPOT_URL = "https://website.spot.ec2.aws.a2z.com/spot.json"
CAPACITY_ROWS = {
    "B300": ("P6-B300 Pricing", "p6-b300.48xlarge", "US West (Oregon)"),
    "B200": ("P6-B200 Pricing", "p6-b200.48xlarge", "US East (Ohio)"),
    "GB200": (
        "P6e Pricing",
        "u-p6e-gb200x72",
        "US East (Dallas) Local Zone",
    ),
}
SPOT_SKUS = {
    "B300": "p6-b300.48xlarge",
    "B200": "p6-b200.48xlarge",
}


def parse_capacity_prices(html: str) -> dict[str, tuple[Decimal, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, tuple[Decimal, str]] = {}
    for model, (heading_text, sku, region) in CAPACITY_ROWS.items():
        heading = next(
            (
                node
                for node in soup.find_all(["h2", "h3"])
                if text(node) == heading_text
            ),
            None,
        )
        if heading is None:
            raise ValueError(f"AWS omitted heading {heading_text}")
        table = heading.find_next("table")
        selected = None
        for row in table.select("tr"):
            cells = [text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) >= 3 and cells[0] == sku and cells[1] == region:
                selected = cells
                break
        if selected is None:
            raise ValueError(f"AWS omitted {sku} in {region}")
        amounts = re.findall(r"\$([0-9.]+)", selected[2])
        if len(amounts) < 2:
            raise ValueError(f"AWS {sku} cell omitted per-accelerator price")
        result[model] = (Decimal(amounts[1]), selected[2])
    return result


def parse_spot_prices(payload: dict[str, object]) -> dict[str, tuple[Decimal, str]]:
    region = next(
        item for item in payload["config"]["regions"] if item["region"] == "us-east-1"
    )
    by_sku: dict[str, str] = {}
    for group in region["instanceTypes"]:
        for size in group.get("sizes", []):
            sku = size.get("size")
            if sku not in SPOT_SKUS.values():
                continue
            linux = next(
                column for column in size["valueColumns"] if column["name"] == "linux"
            )
            by_sku[str(sku)] = linux["prices"]["USD"]
    return {
        model: (Decimal(by_sku[sku]) / Decimal(8), by_sku[sku])
        for model, sku in SPOT_SKUS.items()
    }


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    capacity = parse_capacity_prices(client.get_text(CAPACITY_URL))
    spot = parse_spot_prices(client.get_json(SPOT_URL))
    observations: list[Observation] = []
    for row in rows:
        if row.price_type == "Reserve":
            value, raw = capacity[row.gpu_model_code]
            source_url = CAPACITY_URL
            note = (
                "Published Capacity Block effective hourly rate per accelerator "
                "for the workbook's selected North America region."
            )
        else:
            value, raw = spot[row.gpu_model_code]
            source_url = SPOT_URL
            note = "Current us-east-1 Linux Spot instance price divided by eight GPUs."
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=source_url,
                raw_value=raw,
                note=note,
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("AWS")
