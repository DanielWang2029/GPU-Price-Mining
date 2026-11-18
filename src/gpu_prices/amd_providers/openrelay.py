from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://api.openrelay.inc/v1/public/pricing"
MODELS = {"MI300X", "MI325X", "MI355X"}


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.get_json(URL)
    by_model = {
        item["name"]: item
        for item in payload.get("gpu", [])
        if item.get("manufacturer") == "AMD" and item.get("name") in MODELS
    }
    if set(by_model) != MODELS:
        raise ValueError("OpenRelay API omitted one or more target AMD GPU models")
    offers: list[AmdOffer] = []
    for model, item in sorted(by_model.items()):
        verified = Decimal(str(item["verifiedCents"])) / Decimal(100)
        community = Decimal(str(item["communityCents"])) / Decimal(100)
        offers.append(
            AmdOffer(
                provider_id="openrelay",
                gpu_model_code=model,
                billing_type="ON_DEMAND",
                term_months=0,
                raw_price=verified,
                price_gpu_hour=verified,
                gpu_count=1,
                availability="AVAILABLE",
                source_url=URL,
                gpu_spec=f"{model} verified tier",
                price_note=(
                    f"Verified tier; community tier is ${community}/GPU-hour. "
                    f"Payload generated at {payload.get('generatedAt', '')}."
                ),
            )
        )
    return offers
