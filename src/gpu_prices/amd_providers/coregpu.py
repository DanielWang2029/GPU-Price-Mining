from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://coregpu.io/api/v1/gpus/mi325x"
HOURS_PER_MONTH = Decimal(730)


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    item = client.get_json(URL)
    monthly = Decimal(str(item["price_month"]))
    availability = "AVAILABLE" if int(item.get("available") or 0) > 0 else "UNAVAILABLE"
    return [
        AmdOffer(
            provider_id="coregpu",
            gpu_model_code="MI325X",
            billing_type="RESERVATION",
            term_months=1,
            raw_price=monthly,
            price_gpu_hour=monthly / HOURS_PER_MONTH,
            gpu_count=1,
            availability=availability,
            source_url=URL,
            gpu_spec=str(item.get("slug", "mi325x")),
            price_note=(
                "Published monthly GPU price divided by 730 hours; "
                f"status={item.get('status')}, available={item.get('available')}, "
                f"restock={item.get('restock_on')}."
            ),
        )
    ]
