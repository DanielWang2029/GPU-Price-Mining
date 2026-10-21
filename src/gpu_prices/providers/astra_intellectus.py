from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok, unavailable
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = (
    "https://astra-intellectus.com/wp-json/wp/v2/pages"
    "?slug=gpu-rental&_fields=id,status,modified_gmt,content.rendered"
)
HIDDEN_CLASSES = {
    "elementor-hidden-desktop",
    "elementor-hidden-tablet",
    "elementor-hidden-mobile",
}


def parse_visible_offers(
    rendered_html: str,
) -> dict[str, list[tuple[object, str, str]]]:
    soup = BeautifulSoup(rendered_html, "html.parser")
    result: dict[str, list[tuple[object, str, str]]] = {
        "GB300": [],
        "B300": [],
        "H200": [],
    }
    for table in soup.select("table.bordered-table"):
        hidden = any(
            HIDDEN_CLASSES <= set(parent.get("class", []))
            for parent in table.parents
            if isinstance(parent, Tag)
        )
        if hidden:
            continue
        for row in table.select("tr"):
            cells = [text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) < 6 or not cells[5].startswith("$"):
                continue
            label = cells[0]
            model = next(
                (
                    candidate
                    for candidate in ("GB300", "B300", "H200")
                    if re.search(rf"\b{candidate}\b", label)
                ),
                None,
            )
            if model is not None:
                result[model].append((parse_price(cells[5]), cells[5], label))
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(URL, headers={"Accept": "application/json"})
    if len(payload) != 1:
        raise ValueError(f"Astra WordPress endpoint returned {len(payload)} pages")
    page = payload[0]
    offers = parse_visible_offers(page["content"]["rendered"])
    observations: list[Observation] = []
    for row in rows:
        candidates = offers[row.gpu_model_code]
        if not candidates:
            observations.append(
                unavailable(
                    row,
                    fetched_at=now,
                    source_url=URL,
                    note=(
                        "No visible static Astra offer exists for this exact model; "
                        "stale tables hidden on every viewport were ignored."
                    ),
                )
            )
            continue
        value, raw, label = min(candidates, key=lambda item: item[0])
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                effective_at=page.get("modified_gmt", ""),
                raw_value=raw,
                note=(
                    f"Lowest visible static indicative offer ({label}). Astra's "
                    "browser widget randomizes displayed prices, so deterministic "
                    "server-rendered values are used."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Astra Intellectus")
