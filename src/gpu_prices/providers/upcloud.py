from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

PAGE_URL = "https://upcloud.com/global/products/gpu-servers/"
API_URL = "https://api.upcloud.com/1.3/price"
MIRROR_URL_TEMPLATE = "https://getdeploying.com/gpus/nvidia-{model}"
PLAN_NAMES = {
    ("B200", "On-Demand"): "GPU-24xCPU-240GB-1xB200",
    ("B200", "Spot"): "GPU-SPOT-24xCPU-240GB-1xB200",
    ("B300", "On-Demand"): "GPU-28xCPU-240GB-1xB300",
    ("B300", "Spot"): "GPU-SPOT-28xCPU-240GB-1xB300",
}


def parse_public_page(content: str) -> dict[tuple[str, str], tuple[object, str]]:
    result: dict[tuple[str, str], tuple[object, str]] = {}
    if "<html" in content[:1000].lower() or "<!doctype" in content[:1000].lower():
        soup = BeautifulSoup(content, "html.parser")
        for model in ("B200", "B300"):
            section = soup.select_one(f"#nvidia-{model.lower()}-tab")
            if section is None:
                raise ValueError(f"UpCloud {model} pricing tab was not found")
            matching = None
            for row in section.select("table tbody tr"):
                cells = [text(cell) for cell in row.find_all(["th", "td"])]
                if cells and cells[0].lower() == f"1 x nvidia {model}".lower():
                    matching = cells
                    break
            if matching is None or len(matching) < 5:
                raise ValueError(f"UpCloud one-GPU {model} row was not found")
            result[(model, "Spot")] = (parse_price(matching[3]), matching[3])
            result[(model, "On-Demand")] = (
                parse_price(matching[4]),
                matching[4],
            )
        return result

    for model in ("B200", "B300"):
        match = re.search(
            rf"\|\s*1 x NVIDIA {model}\s*\|[^|]*\|[^|]*\|"
            rf"\s*\**(?P<spot>\$[0-9.]+/h)\**\s*\|"
            rf"\s*\**(?P<ondemand>\$[0-9.]+/h)\**\s*\|",
            content,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"UpCloud proxy output omitted one-GPU {model}")
        for price_type, group in (("Spot", "spot"), ("On-Demand", "ondemand")):
            raw = match.group(group)
            result[(model, price_type)] = (parse_price(raw), raw)
    return result


def parse_getdeploying_mirror(
    content: str,
    model: str,
) -> dict[tuple[str, str], tuple[object, str]]:
    start = content.find("### [UpCloud]")
    if start < 0:
        raise ValueError(f"GetDeploying omitted its UpCloud {model} section")
    end = content.find("\n### [", start + 1)
    section = content[start : end if end >= 0 else None]
    result: dict[tuple[str, str], tuple[object, str]] = {}
    for price_type, label in (("On-Demand", "On-Demand"), ("Spot", "Spot")):
        match = re.search(
            rf"{label}\s+from\s+\$([0-9.]+)",
            section,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(
                f"GetDeploying UpCloud section omitted {model} {price_type}"
            )
        raw = match.group(1)
        result[(model, price_type)] = (parse_price(raw), raw)
    return result


def fetch_api_prices(
    client: HttpClient, token: str
) -> dict[tuple[str, str], tuple[object, str]]:
    payload = client.get_json(
        API_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    prices = payload["prices"]
    if prices["currency"].upper() != "USD":
        raise ValueError(
            f"UpCloud account returned {prices['currency']}; USD is required"
        )
    zones = prices.get("zone", [])
    zone = next((item for item in zones if item.get("name") == "fi-hel2"), None)
    if zone is None:
        raise ValueError("UpCloud API response omitted GPU zone fi-hel2")
    result: dict[tuple[str, str], tuple[object, str]] = {}
    for key, plan in PLAN_NAMES.items():
        raw_credits = zone[f"server_plan_{plan}"]["price"]
        value = Decimal(str(raw_credits)) / Decimal(100)
        result[key] = (value, f"{raw_credits} credits")
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    token = os.getenv("UPCLOUD_TOKEN")
    proxied = False
    mirror_sources: dict[str, str] = {}
    if token:
        prices = fetch_api_prices(client, token)
        source_url = API_URL
        source_note = "Authenticated fi-hel2 catalog price converted from USD cents."
    else:
        try:
            content = client.get_text(PAGE_URL)
            source_url = PAGE_URL
        except FetchError:
            content, source_url = client.read_proxy_text(PAGE_URL)
            proxied = True
        try:
            prices = parse_public_page(content)
            source_note = "Published global USD one-GPU server-hour price."
        except ValueError:
            prices = {}
            for model in ("B200", "B300"):
                mirror_url = MIRROR_URL_TEMPLATE.format(model=model.lower())
                mirror, mirror_source = client.read_proxy_text(mirror_url)
                prices.update(parse_getdeploying_mirror(mirror, model))
                mirror_sources[model] = mirror_source
            source_note = (
                "Published UpCloud USD server-hour price mirrored by GetDeploying; "
                "the UpCloud public page no longer server-renders these tabs."
            )
    if proxied:
        source_note += " Direct access was blocked; public read proxy used."

    observations: list[Observation] = []
    for row in rows:
        value, raw = prices[(row.gpu_model_code, row.price_type)]
        row_source = mirror_sources.get(row.gpu_model_code, source_url)
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=row_source,
                raw_value=raw,
                note=source_note,
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("UpCloud")
