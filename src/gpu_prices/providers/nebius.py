from __future__ import annotations

import json
from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import parse_price, run_provider_cli

PRICES_URL = "https://nebius.com/prices"
SPOT_URL = "https://api.nebius.cloud/billing/v1alpha1/spot-price"
STANDARD_LABELS = {
    "B300": "NVIDIA HGX B300",
    "B200": "NVIDIA HGX B200",
    "H200": "NVIDIA HGX H200",
}
SPOT_REGIONS = {
    ("B300", "North America"): "us-north1",
    ("B300", "United Kingdom"): "uk-south1",
    ("B300", "Europe"): "eu-west2",
    ("B200", "North America"): "us-central1",
    ("B200", "Middle East"): "me-west1",
    ("H200", "Europe"): "eu-west1",
}


def parse_standard_prices(html: str) -> dict[str, tuple[object, str]]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("script#__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("Nebius __NEXT_DATA__ payload was not found")
    next_data = json.loads(script.string)
    apollo = next_data["props"]["pageProps"]["__APOLLO_STATE__"]
    page = next(
        value
        for value in apollo.values()
        if isinstance(value, dict) and value.get("name") == "prices"
    )
    blocks = json.loads(page["content"])["blocks"]
    table = next(
        block["table"]["content"]
        for block in blocks
        if block.get("type") == "highlight-table-block"
        and block.get("title") == "NVIDIA GPU Instances"
    )
    header, *body = table
    price_column = next(
        index for index, value in enumerate(header) if "On-demand" in value
    )
    by_label = {row[0]: row[price_column] for row in body}
    result: dict[str, tuple[object, str]] = {}
    for model, label in STANDARD_LABELS.items():
        raw = by_label.get(label)
        if raw is None:
            raise ValueError(f"Nebius standard table omitted {label}")
        result[model] = (parse_price(raw), raw)
    return result


def fetch_spot_items(client: HttpClient) -> tuple[list[dict[str, object]], str]:
    items: list[dict[str, object]] = []
    page_token = ""
    snapshot_time = ""
    while True:
        params: dict[str, object] = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        payload = client.get_json(
            SPOT_URL, params=params, headers={"Accept": "application/json"}
        )
        items.extend(payload.get("items", []))
        snapshot_time = payload.get("snapshotTime", snapshot_time)
        page_token = payload.get("nextPageToken", "")
        if not page_token:
            return items, snapshot_time


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    standard_rows = [row for row in rows if row.region == "N/A"]
    spot_rows = [row for row in rows if row.region != "N/A"]
    standard = (
        parse_standard_prices(client.get_text(PRICES_URL)) if standard_rows else {}
    )
    spot_items, snapshot_time = fetch_spot_items(client) if spot_rows else ([], "")

    observations: list[Observation] = []
    for row in standard_rows:
        value, raw = standard[row.gpu_model_code]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=PRICES_URL,
                raw_value=raw,
                note="Published on-demand price in USD per GPU-hour.",
            )
        )

    for row in spot_rows:
        exact_region = SPOT_REGIONS[(row.gpu_model_code, row.region)]
        candidates = [
            item
            for item in spot_items
            if item.get("region") == exact_region
            and row.gpu_model_code.lower()
            in item.get("computeInstance", {}).get("platform", "")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one Nebius {row.gpu_model_code} spot item in "
                f"{exact_region}, found {len(candidates)}"
            )
        item = candidates[0]
        raw = item["price"]["value"]
        observations.append(
            ok(
                row,
                money_2(raw),
                fetched_at=now,
                source_url=SPOT_URL,
                effective_at=item.get("effectiveTime", snapshot_time),
                raw_value=str(raw),
                note=(
                    f"Current spot price in {exact_region}, mapped from workbook "
                    f"region {row.region}; USD per GPU-hour."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Nebius")
