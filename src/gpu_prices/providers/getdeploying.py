from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import parse_price, run_provider_cli

URL_TEMPLATE = "https://getdeploying.com/gpus/nvidia-{model}"
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


def _fetch_page(client: HttpClient, url: str) -> tuple[str, str, bool]:
    try:
        return client.get_text(url), url, False
    except FetchError:
        content, proxy_url = client.read_proxy_text(url)
        return content, proxy_url, True


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    by_model: dict[str, tuple[dict[str, tuple[object, str]], str, bool]] = {}
    for model in sorted({row.gpu_model_code for row in rows}):
        url = URL_TEMPLATE.format(model=model.lower())
        content, source_url, proxied = _fetch_page(client, url)
        by_model[model] = (
            parse_history_prices(content),
            source_url,
            proxied,
        )

    observations: list[Observation] = []
    for row in rows:
        prices, source_url, proxied = by_model[row.gpu_model_code]
        item = prices.get(row.price_type)
        note = "Latest weekly provider-median chart value in USD per GPU-hour."
        if proxied:
            note += " Direct access was blocked; public read proxy used."
        if item is None:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=source_url,
                    note=f"{note} Source currently publishes no numeric value.",
                )
            )
            continue
        value, raw = item
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
