from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient
from gpu_prices.providers.common import parse_price
from gpu_prices.providers.daytona import URL, parse_panels


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    panels = parse_panels(client.get_text(URL))
    rows: list[AmdOffer] = []
    for price_type, billing_type in (
        ("On-Demand", "ON_DEMAND"),
        ("Spot", "SPOT"),
    ):
        raw = panels[price_type].get("AMD MI355X")
        if raw is None:
            raise ValueError(f"Daytona omitted AMD MI355X {price_type}")
        price = Decimal(str(parse_price(raw)))
        rows.append(
            AmdOffer(
                provider_id="daytona",
                gpu_model_code="MI355X",
                billing_type=billing_type,
                term_months=0,
                raw_price=price,
                price_gpu_hour=price,
                gpu_count=1,
                availability="AVAILABLE",
                source_url=URL,
                gpu_spec="MI355X GPU-only",
                price_note=(
                    "Published GPU-only rate; CPU, RAM and disk are billed "
                    "separately. Spot maps to Daytona preemptible."
                ),
            )
        )
    return rows
