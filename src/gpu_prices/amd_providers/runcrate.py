from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://www.runcrate.ai/api/gpu-pricing"


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.get_json(URL)
    items = payload.get("gpus", [])
    item = next(row for row in items if row.get("gpu_type") == "MI300X")
    count = min(int(value) for value in item["gpu_counts"])
    per_gpu = Decimal(str(item["min_price_hr"]))
    specs = item.get("specs", {})
    return [
        AmdOffer(
            provider_id="runcrate",
            gpu_model_code="MI300X",
            billing_type="ON_DEMAND",
            term_months=0,
            raw_price=per_gpu,
            price_gpu_hour=per_gpu,
            gpu_count=1,
            availability=(
                "AVAILABLE"
                if int(item.get("available_options") or 0) > 0
                else "UNAVAILABLE"
            ),
            source_url=URL,
            gpu_spec=(
                f"MI300X {count}x {','.join(item.get('deployment_types', []))}; "
                "advertised price is per GPU"
            ),
            cpu_cores=Decimal(str(specs.get("vcpus") or 0)),
            system_ram_gb=Decimal(str(specs.get("memory_gb") or 0)),
            disk_storage_gb=Decimal(str(specs.get("storage_gb") or 0)),
            price_note=(
                f"Public API minimum; regions={item.get('regions')}; "
                f"last_in_stock_at={item.get('last_in_stock_at')}."
            ),
        )
    ]
