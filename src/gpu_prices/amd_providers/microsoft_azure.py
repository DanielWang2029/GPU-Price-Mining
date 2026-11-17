from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://prices.azure.com/api/retail/prices"
SKU = "Standard_ND96isr_MI300X_v5"
REGION = "eastus2"


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    filter_text = (
        f"armSkuName eq '{SKU}' and armRegionName eq '{REGION}' "
        "and priceType eq 'Consumption'"
    )
    payload = client.get_json(URL, params={"$filter": filter_text})
    linux = [
        item
        for item in payload.get("Items", [])
        if "Windows" not in str(item.get("productName", ""))
        and item.get("unitOfMeasure") == "1 Hour"
    ]
    selected: list[tuple[str, dict[str, object]]] = []
    for label, billing_type in (
        ("Spot", "SPOT"),
        ("Low Priority", "SPOT"),
        ("ND96isrMI300Xv5", "ON_DEMAND"),
    ):
        candidates = [
            item
            for item in linux
            if (
                item.get("skuName") == label
                if label == "ND96isrMI300Xv5"
                else str(item.get("skuName", "")).endswith(f" {label}")
            )
        ]
        if len(candidates) != 1:
            raise ValueError(f"Azure expected one Linux {label!r} MI300X price")
        selected.append((billing_type, candidates[0]))
    rows: list[AmdOffer] = []
    for billing_type, item in selected:
        raw = Decimal(str(item["unitPrice"]))
        rows.append(
            AmdOffer(
                provider_id="microsoft-azure",
                gpu_model_code="MI300X",
                billing_type=billing_type,
                term_months=0,
                raw_price=raw,
                price_gpu_hour=raw / 8,
                gpu_count=8,
                availability="AVAILABLE",
                source_url=(
                    f"{URL}?$filter=armSkuName%20eq%20%27{SKU}%27"
                    f"%20and%20armRegionName%20eq%20%27{REGION}%27"
                ),
                gpu_spec=f"{SKU} {item['skuName']} {REGION}",
                cpu_cores=Decimal(96),
                system_ram_gb=Decimal(1850),
                price_note=(
                    "Linux Azure retail consumption price; public catalog does "
                    "not guarantee regional quota or capacity."
                ),
            )
        )
    return rows
