from __future__ import annotations

import csv
import re
from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok, unavailable
from gpu_prices.providers.common import parse_price, run_provider_cli

URL_TEMPLATE = "https://getdeploying.com/gpus/nvidia-{model}"
DATASET_URL_TEMPLATE = "https://getdeploying.com/dataset/gpu-prices/nvidia-{model}.csv"
LABELS = {
    "On-Demand": r"On[\s-]*demand",
    "Reserve": r"Reserved",
    "Spot": r"Spot",
}


def parse_history_prices(content: str) -> dict[str, tuple[object, str]]:
    if "<html" in content[:1000].lower() or "<!doctype" in content[:1000].lower():
        content = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    start = content.lower().find("price history")
    end = content.lower().find("at a glance", start + 1)
    if start < 0 or end < 0:
        raise ValueError("GetDeploying price-history summary was not found")
    summary = content[start:end]
    result: dict[str, tuple[object, str]] = {}
    for price_type, label in LABELS.items():
        match = re.search(rf"{label}\s*\$([0-9][0-9.,]*)", summary, re.IGNORECASE)
        if match:
            raw = match.group(1)
            result[price_type] = (parse_price(raw), raw)
    return result


def parse_dataset_prices(
    content: str,
) -> dict[str, tuple[object, str, str]]:
    rows = list(csv.DictReader(content.splitlines()))
    if not rows:
        raise ValueError("GetDeploying dataset was empty")
    latest_date = max(row["date"] for row in rows)
    latest = [row for row in rows if row["date"] == latest_date]
    result: dict[str, tuple[object, str, str]] = {}

    for price_type, billing_type in (
        ("On-Demand", "ON_DEMAND"),
        ("Spot", "SPOT"),
    ):
        candidates = [
            row
            for row in latest
            if row["billing_type"] == billing_type and row["provider_median_price"]
        ]
        if candidates:
            selected = candidates[0]
            raw = selected["provider_median_price"]
            result[price_type] = (
                money_2(raw),
                raw,
                f"Public weekly dataset dated {latest_date}.",
            )

    reservations = [
        row
        for row in latest
        if row["billing_type"] == "RESERVATION"
        and row["reservation_months"]
        and row["provider_median_price"]
    ]
    if reservations:
        selected = max(
            reservations,
            key=lambda row: (
                int(row["provider_count"]),
                int(row["offering_count"]),
            ),
        )
        raw = selected["provider_median_price"]
        months = selected["reservation_months"]
        result["Reserve"] = (
            money_2(raw),
            f"{raw} ({months} months)",
            (
                f"Public weekly dataset dated {latest_date}; generic Reserve maps "
                f"to the best-covered term ({months} months)."
            ),
        )
    return result


def _fetch_page(client: HttpClient, url: str) -> tuple[str, str, bool]:
    try:
        return client.get_text(url), url, False
    except FetchError:
        content, proxy_url = client.read_proxy_text(url)
        return content, proxy_url, True


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    by_model: dict[str, dict[str, tuple[object, str, str, str]]] = {}
    for model in sorted({row.gpu_model_code for row in rows}):
        url = URL_TEMPLATE.format(model=model.lower())
        content, source_url, proxied = _fetch_page(client, url)
        page_note = "Latest weekly provider-median chart value in USD per GPU-hour."
        if proxied:
            page_note += " Direct access was blocked; public read proxy used."
        entries = {
            price_type: (value, raw, source_url, page_note)
            for price_type, (value, raw) in parse_history_prices(content).items()
        }
        missing = set(LABELS) - set(entries)
        if missing:
            dataset_url = DATASET_URL_TEMPLATE.format(model=model.lower())
            dataset = parse_dataset_prices(client.get_text(dataset_url))
            for price_type in missing:
                if price_type in dataset:
                    value, raw, dataset_note = dataset[price_type]
                    entries[price_type] = (
                        value,
                        raw,
                        dataset_url,
                        dataset_note,
                    )
        by_model[model] = entries

    observations: list[Observation] = []
    for row in rows:
        item = by_model[row.gpu_model_code].get(row.price_type)
        if item is None:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=row.url,
                    note="Source currently publishes no numeric current value.",
                )
            )
            continue
        value, raw, source_url, note = item
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
    run_provider_cli("GetDeploying")
