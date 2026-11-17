from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient
from gpu_prices.providers.common import parse_price, text
from gpu_prices.providers.digitalocean import URL, parse_prices

DOCS_URL = "https://docs.digitalocean.com/products/droplets/details/pricing/"
MARKETING_ROWS = {
    ("MI300X", "On-Demand"),
    ("MI300X", "Reserve"),
    ("MI325X", "On-Demand"),
    ("MI325X", "Reserve"),
    ("MI355X", "Spot"),
}


def parse_docs_prices(html: str) -> dict[tuple[str, str, int], Decimal]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[tuple[str, str, int], Decimal] = {}
    for table in soup.find_all("table"):
        heading = table.find_previous(["h2", "h3", "h4"])
        heading_text = text(heading)
        if "On-Demand GPU" in heading_text:
            billing_type = "ON_DEMAND"
        elif "Spot GPU" in heading_text:
            billing_type = "SPOT"
        else:
            continue
        for row in table.select("tr"):
            cells = [text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) != 2:
                continue
            match = re.fullmatch(r"AMD (MI(?:300|325|355)X)(?: \\((\\d+)x\\))?", cells[0])
            if match is None:
                continue
            count = int(match.group(2) or 1)
            result[(match.group(1), billing_type, count)] = parse_price(cells[1])
    return result


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    marketing = parse_prices(client.get_text(URL))
    docs = parse_docs_prices(client.get_text(DOCS_URL))
    offers: list[AmdOffer] = []
    for model, price_type in sorted(MARKETING_ROWS):
        value = Decimal(str(marketing[(model, price_type)][0]))
        billing_type = {
            "On-Demand": "ON_DEMAND",
            "Reserve": "RESERVATION",
            "Spot": "SPOT",
        }[price_type]
        offers.append(
            AmdOffer(
                provider_id="digitalocean",
                gpu_model_code=model,
                billing_type=billing_type,
                term_months=12 if billing_type == "RESERVATION" else 0,
                raw_price=value,
                price_gpu_hour=value,
                gpu_count=1,
                availability="AVAILABLE",
                source_url=URL,
                gpu_spec=f"{model} published per-GPU card",
                price_note="Published USD per GPU-hour pricing card.",
            )
        )
    for (model, billing_type, count), raw in sorted(docs.items()):
        if count == 1 or model not in {"MI300X", "MI325X", "MI355X"}:
            continue
        offers.append(
            AmdOffer(
                provider_id="digitalocean",
                gpu_model_code=model,
                billing_type=billing_type,
                term_months=0,
                raw_price=raw,
                price_gpu_hour=raw / count,
                gpu_count=count,
                availability="AVAILABLE",
                source_url=DOCS_URL,
                gpu_spec=f"{model} {count}x GPU Droplet",
                price_note="Published node-hour price normalized by GPU count.",
            )
        )
    return offers
