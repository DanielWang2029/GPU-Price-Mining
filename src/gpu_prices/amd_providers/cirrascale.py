from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient
from gpu_prices.providers.common import text

URL = "https://www.cirrascale.com/pricing"


def parse_price_card(html: str) -> Decimal:
    soup = BeautifulSoup(html, "html.parser")
    label = next(
        (
            node
            for node in soup.find_all(string=True)
            if " ".join(str(node).replace("\xa0", " ").split()) == "AMD MI355X"
        ),
        None,
    )
    if label is None:
        raise ValueError("Cirrascale MI355X row was not found")
    row = label.find_parent("div", class_="cro-table_row")
    if row is None:
        raise ValueError("Cirrascale MI355X pricing row was malformed")
    match = re.search(r"\$([0-9.]+)\s*/GPUhr", text(row), re.IGNORECASE)
    if match is None:
        raise ValueError("Cirrascale MI355X row omitted the GPU-hour price")
    return Decimal(match.group(1))


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    price = parse_price_card(client.get_text(URL))
    return [
        AmdOffer(
            provider_id="cirrascale",
            gpu_model_code="MI355X",
            billing_type="RESERVATION",
            term_months=-1,
            raw_price=price,
            price_gpu_hour=price,
            gpu_count=1,
            availability="AVAILABLE",
            source_url=URL,
            gpu_spec="AMD MI355X advertised per-GPU rate",
            price_note=(
                "Published 'as low as' GPU-hour equivalent; Cirrascale states "
                "servers are billed monthly and offers 3/6/12-month blocks."
            ),
        )
    ]
