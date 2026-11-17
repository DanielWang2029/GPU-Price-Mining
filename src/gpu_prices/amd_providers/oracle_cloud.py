from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/"
PRODUCTS = {
    "MI300X": ("B109485", "BM.GPU.MI300X.8"),
    "MI355X": ("B111758", "BM.GPU.MI355X.8"),
}


def _usd_payg(item: dict[str, object]) -> Decimal:
    localizations = item.get("currencyCodeLocalizations", [])
    usd = next(row for row in localizations if row.get("currencyCode") == "USD")
    price = next(row for row in usd["prices"] if row.get("model") == "PAY_AS_YOU_GO")
    return Decimal(str(price["value"]))


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    offers: list[AmdOffer] = []
    for model, (part_number, shape) in PRODUCTS.items():
        payload = client.get_json(
            URL,
            params={"partNumber": part_number, "currencyCode": "USD"},
        )
        item = next(
            row
            for row in payload.get("items", [])
            if row.get("partNumber") == part_number
        )
        per_gpu = _usd_payg(item)
        offers.append(
            AmdOffer(
                provider_id="oracle-cloud",
                gpu_model_code=model,
                billing_type="ON_DEMAND",
                term_months=0,
                raw_price=per_gpu,
                price_gpu_hour=per_gpu,
                gpu_count=1,
                availability="AVAILABLE",
                source_url=f"{URL}?partNumber={part_number}&currencyCode=USD",
                gpu_spec=f"{shape} (8-GPU shape; catalog metric is per GPU)",
                price_note=(
                    "Oracle PAY_AS_YOU_GO GPU-per-hour price; public catalog "
                    f"last updated {payload.get('lastUpdated', '')}."
                ),
            )
        )
    return offers
