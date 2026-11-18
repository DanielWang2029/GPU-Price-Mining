from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://api.vultr.com/v2/plans-metal"
MODELS = {
    "AMD_MI300X": "MI300X",
    "AMD_MI325X": "MI325X",
    "AMD_MI355X": "MI355X",
}


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    payload = client.get_json(URL, params={"per_page": 500})
    offers: list[AmdOffer] = []
    for plan in payload.get("plans_metal", []):
        model = MODELS.get(plan.get("gpu_type"))
        if model is None:
            continue
        count = int(plan["gpu_count"])
        availability = "AVAILABLE" if plan.get("locations") else "UNAVAILABLE"
        common = {
            "provider_id": "vultr",
            "gpu_model_code": model,
            "term_months": 0,
            "gpu_count": count,
            "availability": availability,
            "source_url": URL,
            "gpu_spec": str(plan["id"]),
            "cpu_cores": Decimal(str(plan.get("cpu_count") or 0)),
            "system_ram_gb": Decimal(str(plan.get("ram") or 0)) / Decimal(1024),
            "disk_storage_gb": Decimal(str(plan.get("disk") or 0))
            * Decimal(str(plan.get("disk_count") or 1)),
        }
        hourly = Decimal(str(plan["hourly_cost"]))
        offers.append(
            AmdOffer(
                **common,
                billing_type="ON_DEMAND",
                raw_price=hourly,
                price_gpu_hour=hourly / count,
                price_note=(
                    "Catalog on-demand rate; API currently reports "
                    f"deploy_ondemand={plan.get('deploy_ondemand')} and "
                    f"{len(plan.get('locations') or [])} deployable locations."
                ),
            )
        )
        preemptible = plan.get("hourly_cost_preemptible")
        if preemptible is not None:
            raw = Decimal(str(preemptible))
            offers.append(
                AmdOffer(
                    **common,
                    billing_type="SPOT",
                    raw_price=raw,
                    price_gpu_hour=raw / count,
                    price_note=(
                        "Preemptible rate; API currently reports "
                        f"deploy_preemptible={plan.get('deploy_preemptible')} and "
                        f"{len(plan.get('locations') or [])} deployable locations."
                    ),
                )
            )
    if {offer.gpu_model_code for offer in offers} != set(MODELS.values()):
        raise ValueError("Vultr API omitted one or more target AMD GPU models")
    return offers
