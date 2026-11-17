from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URLS = {
    "MI300X": "https://tensorwave.com/products/accelerators/amd-mi300x",
    "MI325X": "https://tensorwave.com/products/accelerators/amd-mi325x",
    "MI355X": "https://tensorwave.com/products/accelerators/amd-mi355x",
}
PRICE_RE = re.compile(r"Starting at\s+\$([0-9.]+)\s*/GPU HR", re.IGNORECASE)


def parse_price(html: str) -> Decimal:
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)
    match = PRICE_RE.search(text)
    if match is None:
        raise ValueError("TensorWave starting price was not found")
    return Decimal(match.group(1))


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    rows: list[AmdOffer] = []
    for model, url in URLS.items():
        price = parse_price(client.get_text(url))
        rows.append(
            AmdOffer(
                provider_id="tensorwave",
                gpu_model_code=model,
                billing_type="RESERVATION",
                term_months=-1,
                raw_price=price,
                price_gpu_hour=price,
                gpu_count=1,
                availability="AVAILABLE",
                source_url=url,
                gpu_spec=f"8x {model} OAM node; advertised price is per GPU",
                price_note=(
                    "Advertised starting price; TensorWave documents customized "
                    "reservations and does not expose live stock."
                ),
            )
        )
    return rows
