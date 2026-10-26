from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.daytona.io/pricing"
PANEL_LABELS = {
    "On-Demand": "On-demand GPU prices per hour",
    "Spot": "Preemptible GPU prices per hour",
}


def parse_panels(html: str) -> dict[str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, dict[str, str]] = {}
    for price_type, label in PANEL_LABELS.items():
        copies: list[dict[str, str]] = []
        for panel in soup.select(f'[role="tabpanel"][aria-label="{label}"]'):
            values: dict[str, str] = {}
            for container in panel.find_all("div"):
                name = container.select_one('[data-framer-name="GPU Name"]')
                price = container.select_one('[data-framer-name="GPU Price"]')
                if name is not None and price is not None:
                    values[text(name)] = text(price)
            if values:
                copies.append(values)
        if not copies:
            raise ValueError(f"Daytona panel {label!r} was not found")
        if any(copy != copies[0] for copy in copies[1:]):
            raise ValueError(f"Daytona responsive copies disagree for {label!r}")
        result[price_type] = copies[0]
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    panels = parse_panels(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        raw = panels[row.price_type].get(f"Nvidia {row.gpu_model_code}", "")
        if not raw:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=(
                        f"Daytona's current {row.price_type} panel does not list "
                        f"{row.gpu_model_code}; no stale price was carried forward."
                    ),
                )
            )
            continue
        observations.append(
            ok(
                row,
                parse_price(raw),
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note=(
                    "Published GPU-only rate in USD per GPU-hour; Spot maps to "
                    "Daytona's Preemptible tier."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Daytona")
