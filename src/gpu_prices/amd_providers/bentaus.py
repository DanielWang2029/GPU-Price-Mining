from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient
from gpu_prices.providers.bentaus import parse_ranges

URLS = {
    "MI325X": "https://www.bentaus.com/amd-mi325x",
    "MI355X": "https://www.bentaus.com/amd-mi355x",
}


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    rows: list[AmdOffer] = []
    for model, url in URLS.items():
        prices = parse_ranges(client.get_text(url))
        for price_type, billing_type in (
            ("On-Demand", "ON_DEMAND"),
            ("Reserve", "RESERVATION"),
        ):
            value = Decimal(prices[price_type][0])
            rows.append(
                AmdOffer(
                    provider_id="bentaus",
                    gpu_model_code=model,
                    billing_type=billing_type,
                    term_months=-1 if billing_type == "RESERVATION" else 0,
                    raw_price=value,
                    price_gpu_hour=value,
                    gpu_count=1,
                    availability="AVAILABLE",
                    source_url=url,
                    gpu_spec=f"{model} advertised per-GPU rate",
                    price_note=(
                        "Published per-GPU-hour price; reservation duration and "
                        "live stock are not exposed."
                    ),
                )
            )
    return rows
