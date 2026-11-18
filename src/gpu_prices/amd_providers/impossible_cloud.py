from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://console.impossiblecloud.com/api/gpu/offers"


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.get_json(URL)
    offer = next(
        item
        for item in payload.get("offers", [])
        if item.get("gpuModel") == "MI355X"
    )
    count = int(offer["gpusPerNode"])
    availability = (
        "AVAILABLE"
        if offer.get("availability", {}).get("now") is True
        else "WAITLIST"
    )
    rows: list[AmdOffer] = []
    for price in offer.get("pricing", []):
        term = int(price["durationMonths"])
        per_gpu = Decimal(str(price["pricePerGpuHour"]))
        rows.append(
            AmdOffer(
                provider_id="impossible-cloud",
                gpu_model_code="MI355X",
                billing_type="RESERVATION",
                term_months=term,
                raw_price=per_gpu,
                price_gpu_hour=per_gpu,
                gpu_count=1,
                availability=availability,
                source_url=URL,
                gpu_spec=f"{offer['sku']} ({count}-GPU node; price is per GPU)",
                system_ram_gb=Decimal(2304),
                price_note=(
                    f"{offer.get('region', '')} reserved offer; status "
                    f"{offer.get('availability', {}).get('status', '')}, "
                    f"immediate={offer.get('availability', {}).get('now')}."
                ),
            )
        )
    if not rows:
        raise ValueError("Impossible Cloud MI355X offer had no prices")
    return rows
