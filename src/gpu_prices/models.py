from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Status = Literal["ok", "unavailable", "error"]


@dataclass(frozen=True, slots=True)
class SourceRow:
    workbook_row: int
    source_name: str
    gpu_model_code: str
    price_type: str
    region: str
    cloud_type: str
    url: str
    supplier_type: str = "N/A"
    term: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    row: SourceRow
    price: Decimal | None
    status: Status
    fetched_at: datetime
    source_url: str
    effective_at: str = ""
    raw_value: str = ""
    note: str = ""


def as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money_2(value: object) -> Decimal:
    return as_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ok(
    row: SourceRow,
    price: object,
    *,
    fetched_at: datetime,
    source_url: str,
    effective_at: str = "",
    raw_value: str = "",
    note: str = "",
) -> Observation:
    return Observation(
        row=row,
        price=as_decimal(price),
        status="ok",
        fetched_at=fetched_at,
        source_url=source_url,
        effective_at=effective_at,
        raw_value=raw_value or str(price),
        note=note,
    )


def unavailable(
    row: SourceRow,
    *,
    fetched_at: datetime,
    source_url: str,
    note: str,
) -> Observation:
    return Observation(
        row=row,
        price=None,
        status="unavailable",
        fetched_at=fetched_at,
        source_url=source_url,
        note=note,
    )


def failed(
    row: SourceRow,
    *,
    fetched_at: datetime,
    source_url: str,
    note: str,
) -> Observation:
    return Observation(
        row=row,
        price=None,
        status="error",
        fetched_at=fetched_at,
        source_url=source_url,
        note=note,
    )
