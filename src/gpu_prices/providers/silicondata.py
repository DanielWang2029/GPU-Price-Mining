from __future__ import annotations

import html as html_module
import json
import re
import time
from datetime import datetime
from decimal import Decimal

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli

URL_TEMPLATE = "https://www.silicondata.com/products/silicon-index/{model}"


def _normalize_payload(html: str) -> str:
    return html_module.unescape(html).replace(r"\"", '"')


def parse_index_page(html: str) -> tuple[object, str, str]:
    normalized = _normalize_payload(html)
    match = re.search(
        r'"rawValue":"(?P<value>[^"]+)".{0,300}?'
        r'"asOf":"(?P<as_of>[^"]+)"',
        normalized,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Silicon Data structured index payload was not found")
    raw = match.group("value")
    return parse_price(raw), raw, match.group("as_of")


def parse_index_history(html: str) -> dict[str, Decimal]:
    normalized = _normalize_payload(html)
    index_start = normalized.find('"rawValue":')
    points_marker = '"points":'
    points_start = normalized.find(points_marker, index_start)
    if index_start < 0 or points_start < 0:
        raise ValueError("Silicon Data structured history payload was not found")
    points, _ = json.JSONDecoder().raw_decode(
        normalized[points_start + len(points_marker) :]
    )
    if not isinstance(points, list):
        raise ValueError("Silicon Data points payload was not a list")
    return {
        str(point["date"]): parse_price(point["price"])
        for point in points
        if isinstance(point, dict) and "date" in point and "price" in point
    }


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    observations: list[Observation] = []
    for row in rows:
        url = URL_TEMPLATE.format(model=row.gpu_model_code.lower())
        parsed = None
        last_error: ValueError | None = None
        for attempt in range(4):
            page = client.get_text(
                url,
                params={"collector_retry": f"{int(now.timestamp())}-{attempt}"},
                headers={"Cache-Control": "no-cache"},
            )
            try:
                parsed = parse_index_page(page)
                break
            except ValueError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.5 * (attempt + 1))
        if parsed is None:
            raise last_error or ValueError("Silicon Data index payload was absent")
        value, raw, effective_at = parsed
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=url,
                effective_at=effective_at,
                raw_value=raw,
                note="Published Neo-Cloud rental price index in USD per GPU-hour.",
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("SiliconData")
