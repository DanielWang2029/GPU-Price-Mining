from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from gpu_prices.amd_prices import AmdOffer
from gpu_prices.http import HttpClient

URL = "https://hotaisle.xyz/pricing"
VM_PRICE_RE = re.compile(r"Virtual machines\s+\$([0-9.]+)/GPU/hr", re.IGNORECASE)
BARE_METAL_RE = re.compile(
    r"Bare metal Large 8x MI300x\s+\$([0-9.]+)/GPU/hr",
    re.IGNORECASE,
)


def parse_prices(html: str) -> tuple[Decimal, Decimal]:
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)
    vm_match = VM_PRICE_RE.search(text)
    bare_match = BARE_METAL_RE.search(text)
    if vm_match is None or bare_match is None:
        raise ValueError("Hot Aisle MI300X prices were not found")
    return Decimal(vm_match.group(1)), Decimal(bare_match.group(1))


def collect(client: HttpClient, _now: datetime) -> list[AmdOffer]:
    vm_price, bare_price = parse_prices(client.get_text(URL))
    return [
        AmdOffer(
            provider_id="hotaisle",
            gpu_model_code="MI300X",
            billing_type="ON_DEMAND",
            term_months=0,
            raw_price=vm_price,
            price_gpu_hour=vm_price,
            gpu_count=1,
            availability="AVAILABLE",
            source_url=URL,
            gpu_spec="MI300X 1x/2x/4x VMs; advertised price is per GPU",
            price_note="Published VM per-GPU rate, billed by the minute.",
        ),
        AmdOffer(
            provider_id="hotaisle",
            gpu_model_code="MI300X",
            billing_type="ON_DEMAND",
            term_months=0,
            raw_price=bare_price,
            price_gpu_hour=bare_price,
            gpu_count=1,
            availability="AVAILABLE",
            source_url=URL,
            gpu_spec="MI300X 8x bare metal; advertised price is per GPU",
            price_note="Published dedicated bare-metal per-GPU rate.",
        ),
    ]
