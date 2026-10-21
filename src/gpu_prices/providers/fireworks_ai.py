from __future__ import annotations

from datetime import datetime

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli

URL = "https://pv37i0yn.api.sanity.io/v2024-07-09/data/query/production"
QUERY = """
*[_type=="page" && seo.slug.current=="pricing"][0]{
  _updatedAt,
  "table": body[
    _type=="tableBlock" && heading=="On demand deployments"
  ][0].table{
    columnHeaders[]{cellIndex,title},
    rows[]{cells[]{"text":pt::text(content)}}
  }
}
""".strip()


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    payload = client.get_json(URL, params={"query": QUERY})
    result = payload.get("result") or {}
    table = result.get("table") or {}
    headers = {
        item["title"]: int(item["cellIndex"]) for item in table.get("columnHeaders", [])
    }
    model_column = headers.get("GPU Type")
    price_column = headers.get("Price ($) per hour")
    if model_column is None or price_column is None:
        raise ValueError("Fireworks on-demand deployment columns changed")
    prices: dict[str, tuple[object, str]] = {}
    for row_data in table.get("rows", []):
        cells = [cell.get("text", "") for cell in row_data.get("cells", [])]
        if max(model_column, price_column) >= len(cells):
            continue
        model = cells[model_column].split()[0]
        raw = cells[price_column]
        prices[model] = (parse_price(raw), raw)

    observations: list[Observation] = []
    for row in rows:
        value, raw = prices[row.gpu_model_code]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                effective_at=result.get("_updatedAt", ""),
                raw_value=raw,
                note=(
                    "Published base on-demand deployment price in USD per GPU-hour; "
                    "region premiums are excluded."
                ),
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Fireworks.ai")
