from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import parse_price, run_provider_cli

URL = "https://cyfuture.ai/pricing"
FX_URL = "https://api.frankfurter.app/latest"
TERM_COLUMNS = {1: 11, 6: 12, 12: 13}


def parse_b300_row(markdown: str) -> list[str]:
    for line in markdown.splitlines():
        if line.lstrip().startswith("| 1B300.32v.256m |"):
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
    raise ValueError("Cyfuture B300 single-GPU pricing row was not found")


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    try:
        content = client.get_text(URL)
        source_url = URL
    except FetchError:
        content, source_url = client.read_proxy_text(URL)
    cells = parse_b300_row(content)
    fx = client.get_json(
        FX_URL,
        params={"from": "USD", "to": "INR"},
    )
    inr_per_usd = Decimal(str(fx["rates"]["INR"]))
    observations: list[Observation] = []
    for row in rows:
        if row.term is None or int(row.term) not in TERM_COLUMNS:
            raise ValueError(f"Unsupported Cyfuture term {row.term}")
        term = int(row.term)
        raw = cells[TERM_COLUMNS[term]]
        inr = parse_price(raw)
        observations.append(
            ok(
                row,
                money_2(inr / inr_per_usd),
                fetched_at=now,
                source_url=source_url,
                effective_at=fx.get("date", ""),
                raw_value=f"INR {inr} / {inr_per_usd} INR per USD",
                note=(
                    f"Published {term}-month INR/GPU-hour rate converted with "
                    "Frankfurter's current USD/INR reference rate."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Cyfuture.ai")
