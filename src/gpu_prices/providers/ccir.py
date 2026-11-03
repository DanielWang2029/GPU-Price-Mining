from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import run_provider_cli

URL = "https://ccir.io/discovery"
ZONES = {
    ("B300", "North America"): "b300-northern-virginia-z6",
    ("B300", "Europe"): "b300-london-z4",
    ("B300", "Asia-Pacific"): "b300-seoul-z3",
    ("B200", "North America"): "b200-northern-virginia-z6",
    ("B200", "Europe"): "b200-paris-z1",
    ("B200", "Asia-Pacific"): "b200-mumbai-z2",
    ("H200", "North America"): "h200-upgraded-northern-virginia-z2",
    ("H200", "Europe"): "h200-standard-london-z2",
    ("H200", "Asia-Pacific"): "h200-upgraded-seoul-z1",
}


def parse_payload(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("script#disc-data")
    if script is None or not script.string:
        raise ValueError("CCIR discovery payload was not found")
    return json.loads(script.string, parse_float=Decimal)


def series_by_zone(
    payload: dict[str, object],
) -> dict[str, dict[date, Decimal]]:
    result: dict[str, dict[date, Decimal]] = {}
    for row in payload.get("rows", []):
        zone_id = row.get("id")
        if zone_id not in ZONES.values():
            continue
        start = date.fromisoformat(row["start"])
        result[str(zone_id)] = {
            start + timedelta(days=int(offset)): Decimal(str(value))
            for offset, value in row.get("p", [])
        }
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = parse_payload(client.get_text(URL))
    series = series_by_zone(payload)
    observations: list[Observation] = []
    for row in rows:
        zone_id = ZONES[(row.gpu_model_code, row.region)]
        points = series.get(zone_id)
        if not points:
            raise ValueError(f"CCIR omitted zone {zone_id}")
        effective_date = max(points)
        raw = points[effective_date]
        observations.append(
            ok(
                row,
                money_2(raw),
                fetched_at=now,
                source_url=URL,
                raw_price=raw,
                gpu_count=1,
                availability="AVAILABLE",
                effective_at=effective_date.isoformat(),
                raw_value=str(raw),
                note=(
                    f"CCIR zone {zone_id}; embedded rate is already USD per "
                    "GPU-hour. Price presence does not assert EC2 capacity."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("CCIR")
