from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from gpu_prices.models import Observation

SOURCE_LABEL = "GPU INDEX"
BILLING_TYPE = "ON_DEMAND"
TERM_MONTHS = "0"
PROVIDER_SERIES_COLUMNS = [
    "price_date",
    "run_date",
    "gpu_id",
    "gpu_model_code",
    "billing_type",
    "term_months",
    "provider_id",
    "median_price",
    "offering_count",
    "supplier_type",
    "reference_url",
    "source_label",
]
GPU_IDS = {
    "A100": "nvidia-a100",
    "B200": "nvidia-b200",
    "B300": "nvidia-b300",
    "GB200": "nvidia-gb200",
    "GB300": "nvidia-gb300",
    "H100": "nvidia-h100",
    "H200": "nvidia-h200",
    "MI300X": "amd-mi300x",
}


@dataclass(frozen=True, slots=True)
class IndexRoute:
    provider_id: str
    supplier_type: str
    reference_url: str
    source_names: frozenset[str]


ROUTES = (
    IndexRoute(
        provider_id="computedesk",
        supplier_type="Serverless",
        reference_url="https://www.computedesk.com/indexes-overview",
        source_names=frozenset({"Compute Desk"}),
    ),
    IndexRoute(
        provider_id="ornn",
        supplier_type="Serverless",
        reference_url="https://data.ornn.com/",
        source_names=frozenset({"Ornn"}),
    ),
    IndexRoute(
        provider_id="silicondata",
        supplier_type="GPU Cloud",
        reference_url="https://portal.silicondata.com/silicon-index",
        source_names=frozenset({"SiliconData", "Silicon Data"}),
    ),
)
ROUTES_BY_PROVIDER_ID = {route.provider_id: route for route in ROUTES}
ROUTES_BY_SOURCE_NAME = {
    source_name: route
    for route in ROUTES
    for source_name in route.source_names
}
def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def route_for(
    *,
    source_name: str = "",
    provider_id: str = "",
) -> IndexRoute | None:
    return ROUTES_BY_PROVIDER_ID.get(provider_id) or ROUTES_BY_SOURCE_NAME.get(
        source_name
    )


def is_gpu_index(
    *,
    source_name: str = "",
    provider_id: str = "",
) -> bool:
    return route_for(source_name=source_name, provider_id=provider_id) is not None


def split_detail_rows(
    rows: Iterable[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    detail_rows: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []
    for row in rows:
        target = (
            index_rows
            if is_gpu_index(
                source_name=row.get("publisher_name", ""),
                provider_id=row.get("provider_id", ""),
            )
            else detail_rows
        )
        target.append(row)
    return detail_rows, index_rows


def split_observations(
    observations: Iterable[Observation],
) -> tuple[list[Observation], list[Observation]]:
    detail_observations: list[Observation] = []
    index_observations: list[Observation] = []
    for observation in observations:
        target = (
            index_observations
            if is_gpu_index(source_name=observation.row.source_name)
            else detail_observations
        )
        target.append(observation)
    return detail_observations, index_observations


def _provider_series_row(
    *,
    price_date: str,
    run_date: str,
    model: str,
    price: Decimal,
    route: IndexRoute,
) -> dict[str, str]:
    try:
        gpu_id = GPU_IDS[model]
    except KeyError as exc:
        raise ValueError(f"No GPU dimension mapping for index model {model!r}") from exc
    return {
        "price_date": price_date,
        "run_date": run_date,
        "gpu_id": gpu_id,
        "gpu_model_code": model,
        "billing_type": BILLING_TYPE,
        "term_months": TERM_MONTHS,
        "provider_id": route.provider_id,
        "median_price": _number(price),
        "offering_count": "1",
        "supplier_type": route.supplier_type,
        "reference_url": route.reference_url,
        "source_label": SOURCE_LABEL,
    }


def _validate_unique(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = (
            row["price_date"],
            row["gpu_id"],
            row["billing_type"],
            row["term_months"],
            row["provider_id"],
        )
        if key in seen:
            raise ValueError(f"Duplicate GPU INDEX provider-series row: {key}")
        seen.add(key)
    return sorted(
        rows,
        key=lambda row: (
            row["price_date"],
            row["gpu_model_code"],
            row["provider_id"],
        ),
    )


def rows_from_observations(
    observations: Iterable[Observation],
    *,
    price_date: str,
    run_date: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for observation in observations:
        route = route_for(source_name=observation.row.source_name)
        if route is None:
            continue
        if observation.price_gpu_hour is None:
            continue
        rows.append(
            _provider_series_row(
                price_date=price_date,
                run_date=run_date,
                model=observation.row.gpu_model_code,
                price=observation.price_gpu_hour,
                route=route,
            )
        )
    return _validate_unique(rows)


def rows_from_detail(
    rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        route = route_for(
            source_name=row.get("publisher_name", ""),
            provider_id=row.get("provider_id", ""),
        )
        if route is None or not row.get("price_gpu_hour"):
            continue
        output.append(
            _provider_series_row(
                price_date=row["price_date"],
                run_date=row["run_date"],
                model=row["gpu_model_code"],
                price=Decimal(row["price_gpu_hour"]),
                route=route,
            )
        )
    return _validate_unique(output)


def merge_rows(
    *groups: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    for rows in groups:
        for row in rows:
            key = (
                row["price_date"],
                row["gpu_id"],
                row["billing_type"],
                row["term_months"],
                row["provider_id"],
            )
            if key in merged and merged[key] != row:
                raise ValueError(f"Conflicting GPU INDEX provider-series row: {key}")
            merged[key] = row
    return _validate_unique(list(merged.values()))


def output_path(output_dir: Path, price_date: str) -> Path:
    return output_dir / f"gpu_index_provider_series_daily_{price_date}.csv"


def write_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=PROVIDER_SERIES_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != PROVIDER_SERIES_COLUMNS:
            raise ValueError(
                f"Unexpected GPU INDEX columns in {path}: {reader.fieldnames}"
            )
        rows = list(reader)
    for row in rows:
        if row["source_label"] != SOURCE_LABEL:
            raise ValueError(f"{path} contains non-GPU INDEX source labels")
        if row["billing_type"] != BILLING_TYPE or row["term_months"] != TERM_MONTHS:
            raise ValueError(f"{path} contains invalid GPU INDEX billing metadata")
        if row["provider_id"] not in ROUTES_BY_PROVIDER_ID:
            raise ValueError(
                f"{path} contains unknown GPU INDEX provider {row['provider_id']!r}"
            )
        Decimal(row["median_price"])
    return _validate_unique(rows)
