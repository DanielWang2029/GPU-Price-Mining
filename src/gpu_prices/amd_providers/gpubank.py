from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://gpubank.io/prices.json"
PRICE_FIELDS = {
    "ON_DEMAND": ("on_demand_per_hour", 0),
    "SPOT": ("interruptible_per_hour", 0),
    "RESERVATION": ("reserved_month_per_hour", 1),
}


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.get_json(URL)
    item = next(row for row in payload.get("gpus", []) if row.get("sku") == "mi300x")
    allocatable = sum(
        int(region.get("allocatable") or 0)
        for region in item.get("regions", {}).values()
    )
    availability = "AVAILABLE" if allocatable > 0 else "UNAVAILABLE"
    rows: list[AmdOffer] = []
    for billing_type, (field, term) in PRICE_FIELDS.items():
        value = Decimal(str(item["price"][field]))
        rows.append(
            AmdOffer(
                provider_id="gpubank",
                gpu_model_code="MI300X",
                billing_type=billing_type,
                term_months=term,
                raw_price=value,
                price_gpu_hour=value,
                gpu_count=1,
                availability=availability,
                source_url=URL,
                gpu_spec=str(item["sku"]),
                cpu_cores=Decimal(str(item.get("included", {}).get("vcpu") or 0)),
                system_ram_gb=Decimal(
                    str(item.get("included", {}).get("ram_gb") or 0)
                ),
                price_note=(
                    f"Public per-second catalog; {allocatable} GPUs allocatable "
                    f"across regions; generated {payload.get('generated_at', '')}."
                ),
            )
        )
    return rows
