from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://api.runpod.io/graphql"
QUERY = """
query {
  gpuTypes {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    securePrice
    communityPrice
  }
}
"""
GPU_ID = "AMD Instinct MI300X OAM"


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.post_json(
        URL,
        json={"query": QUERY},
        headers={"Content-Type": "application/json"},
    )
    if payload.get("errors"):
        raise ValueError(f"RunPod GraphQL returned errors: {payload['errors']}")
    item = next(
        row
        for row in payload.get("data", {}).get("gpuTypes", [])
        if row.get("id") == GPU_ID
    )
    price = Decimal(str(item["securePrice"]))
    return [
        AmdOffer(
            provider_id="runpod",
            gpu_model_code="MI300X",
            billing_type="ON_DEMAND",
            term_months=0,
            raw_price=price,
            price_gpu_hour=price,
            gpu_count=1,
            availability=(
                "AVAILABLE" if item.get("secureCloud") is True else "UNAVAILABLE"
            ),
            source_url=URL,
            gpu_spec=GPU_ID,
            price_note=(
                "Secure Cloud catalog rate; the public GPU-type response reports "
                f"secureCloud={item.get('secureCloud')} but not live stock."
            ),
        )
    ]
