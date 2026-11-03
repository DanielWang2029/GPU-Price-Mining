from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Status = Literal["ok", "unavailable", "error"]
Availability = Literal["AVAILABLE", "UNAVAILABLE", "WAITLIST", ""]


@dataclass(frozen=True, slots=True)
class SourceRow:
    workbook_row: int
    source_name: str
    gpu_model_code: str
    price_type: str
    region: str
    url: str
    supplier_type: str = ""
    term: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    row: SourceRow
    raw_price: Decimal | None
    price_gpu_hour: Decimal | None
    gpu_count: int
    availability: Availability
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
    price_gpu_hour: object,
    *,
    fetched_at: datetime,
    source_url: str,
    raw_price: object | None = None,
    gpu_count: int = 1,
    effective_at: str = "",
    raw_value: str = "",
    note: str = "",
) -> Observation:
    if gpu_count < 1:
        raise ValueError(f"GPU count must be positive, got {gpu_count}")
    normalized = as_decimal(price_gpu_hour)
    return Observation(
        row=row,
        raw_price=normalized if raw_price is None else as_decimal(raw_price),
        price_gpu_hour=normalized,
        gpu_count=gpu_count,
        availability="AVAILABLE",
        status="ok",
        fetched_at=fetched_at,
        source_url=source_url,
        effective_at=effective_at,
        raw_value=raw_value or str(raw_price if raw_price is not None else normalized),
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
        raw_price=None,
        price_gpu_hour=None,
        gpu_count=1,
        availability="UNAVAILABLE",
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
        raw_price=None,
        price_gpu_hour=None,
        gpu_count=1,
        availability="",
        status="error",
        fetched_at=fetched_at,
        source_url=source_url,
        note=note,
    )
