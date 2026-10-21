from __future__ import annotations

import re
import sys
from datetime import datetime
from decimal import Decimal
from typing import Callable, Iterable

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow

Collector = Callable[
    [list[SourceRow], HttpClient, datetime],
    list[Observation],
]

PRICE_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def parse_price(value: object) -> Decimal:
    match = PRICE_RE.search(str(value))
    if not match:
        raise ValueError(f"No numeric price in {value!r}")
    return Decimal(match.group(0).replace(",", ""))


def text(node: object) -> str:
    strings = getattr(node, "stripped_strings", ())
    return " ".join(" ".join(strings).replace("\xa0", " ").split())


def require_rows(
    rows: Iterable[SourceRow],
    expected: Iterable[tuple[str, str, str]],
) -> None:
    actual = {(row.gpu_model_code, row.price_type, row.cloud_type) for row in rows}
    required = set(expected)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise ValueError(f"Workbook mappings changed; missing={missing}, extra={extra}")


def run_provider_cli(source_name: str) -> None:
    from gpu_prices.collect import main

    raise SystemExit(main(["--provider", source_name, *sys.argv[1:]]))
