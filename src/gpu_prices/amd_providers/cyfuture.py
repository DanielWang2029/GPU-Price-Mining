from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import money_2
from gpu_prices.providers.common import parse_price, text

URL = "https://cyfuture.ai/pricing"
FX_URL = "https://api.frankfurter.app/latest"
MODEL_MARKERS = {
    "MI300X": "MI300",
    "MI325X": "MI325",
}
PRICE_COLUMNS = (
    ("ON_DEMAND", 0, 10),
    ("RESERVATION", 1, 11),
    ("RESERVATION", 6, 12),
    ("RESERVATION", 12, 13),
)


def parse_rows(content: str) -> dict[str, list[list[str]]]:
    parsed: dict[str, list[list[str]]] = {model: [] for model in MODEL_MARKERS}
    seen: set[str] = set()
    for line in content.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in seen:
            continue
        for model, marker in MODEL_MARKERS.items():
            if marker in cells[0].upper() and len(cells) > 13:
                parsed[model].append(cells)
                seen.add(cells[0])
                break
    if all(parsed.values()):
        return parsed

    soup = BeautifulSoup(content, "html.parser")
    for row in soup.select("tr"):
        cells = [text(cell) for cell in row.find_all("td")]
        if not cells or cells[0] in seen:
            continue
        for model, marker in MODEL_MARKERS.items():
            if marker in cells[0].upper() and len(cells) > 13:
                parsed[model].append(cells)
                seen.add(cells[0])
                break
    if not all(parsed.values()):
        raise ValueError("Cyfuture AMD pricing rows were not found")
    return parsed


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    try:
        content = client.get_text(URL)
        source_url = URL
    except FetchError:
        content, _ = client.read_proxy_text(URL)
        source_url = URL
    by_model = parse_rows(content)
    fx = client.get_json(FX_URL, params={"from": "USD", "to": "INR"})
    inr_per_usd = Decimal(str(fx["rates"]["INR"]))
    offers: list[AmdOffer] = []
    for model, rows in by_model.items():
        for cells in rows:
            count = int(parse_price(cells[1].split("(", 1)[1]))
            cpu_cores = parse_price(cells[5])
            ram_gb = parse_price(cells[6])
            for billing_type, term, column in PRICE_COLUMNS:
                inr = parse_price(cells[column])
                offers.append(
                    AmdOffer(
                        provider_id="cyfuture",
                        gpu_model_code=model,
                        billing_type=billing_type,
                        term_months=term,
                        raw_price=inr,
                        price_gpu_hour=money_2((inr / inr_per_usd) / count),
                        gpu_count=count,
                        availability="AVAILABLE",
                        source_url=source_url,
                        gpu_spec=cells[0],
                        cpu_cores=cpu_cores,
                        system_ram_gb=ram_gb,
                        price_note=(
                            f"Published INR node-hour price converted at "
                            f"{inr_per_usd} INR/USD ({fx.get('date', '')})."
                        ),
                    )
                )
    return offers
