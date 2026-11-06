from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook

from gpu_prices.workbook import make_record_id

DETAIL_TABLE = "public.compute_insight_gpu_price_detail_daily"
PROVIDER_SERIES_TABLE = "public.compute_insight_gpu_provider_series_daily"
PRICE_SERIES_TABLE = "public.compute_insight_gpu_price_series_daily"
DIM_PROVIDER_TABLE = "public.compute_insight_dim_provider"

DETAIL_COLUMNS = [
    "price_date",
    "run_date",
    "source_label",
    "record_id",
    "publisher_name",
    "provider_id",
    "supplier_type",
    "gpu_id",
    "gpu_model_code",
    "gpu_count",
    "gpu_spec",
    "vram_per_gpu_gb",
    "vram_total_gb",
    "cpu_cores",
    "system_ram_gb",
    "disk_storage_gb",
    "interconnect_bandwidth_gbps",
    "gpu_mem_bandwidth_gbps",
    "billing_type",
    "term_months",
    "region_or_hq_country",
    "provider_hq_region",
    "raw_price",
    "price_gpu_hour",
    "availability",
    "price_note",
    "source_url",
]
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
PRICE_SERIES_COLUMNS = [
    "price_date",
    "run_date",
    "gpu_id",
    "gpu_model_code",
    "billing_type",
    "term_months",
    "supplier_type",
    "region_group",
    "median_price",
    "p25_price",
    "p75_price",
    "min_price",
    "offering_count",
    "source_label",
]
DIM_PROVIDER_COLUMNS = [
    "provider_id",
    "provider_name",
    "website",
    "region_or_hq_country",
    "provider_hq_region",
    "supplier_type",
    "tier_confidence",
    "updated_at",
]

NUMERIC_COLUMNS = {
    "gpu_count",
    "vram_per_gpu_gb",
    "vram_total_gb",
    "cpu_cores",
    "system_ram_gb",
    "disk_storage_gb",
    "interconnect_bandwidth_gbps",
    "gpu_mem_bandwidth_gbps",
    "term_months",
    "raw_price",
    "price_gpu_hour",
    "median_price",
    "p25_price",
    "p75_price",
    "min_price",
    "offering_count",
}

GPU_IDS = {
    "A100": "nvidia-a100",
    "B200": "nvidia-b200",
    "B300": "nvidia-b300",
    "GB200": "nvidia-gb200",
    "GB300": "nvidia-gb300",
    "H200": "nvidia-h200",
}

PROVIDER_IDS = {
    "Kalshi": "kalshi",
    "Ornn": "ornn",
    "CoreWeave": "coreweave",
    "SiliconData": "silicondata",
    "Nebius": "nebius",
    "GetDeploying": "getdeploying",
    "RunPod": "runpod",
    "Together.ai": "together-ai",
    "Daytona": "daytona",
    "UpCloud": "upcloud",
    "Gpu.ai": "gpu-ai",
    "Spheron": "spheron",
    "Hyperbolic": "hyperbolic",
    "DeepInfra": "deepinfra",
    "Fireworks.ai": "fireworks-ai",
    "Astra Intellectus": "astra-intellectus",
    "Verda": "verda",
    "Impossible Cloud": "impossible-cloud",
    "TheAI Cloud": "theai-cloud",
    "Digital Ocean": "digitalocean",
    "Bentaus": "bentaus",
    "Civo": "civo",
    "Cyfuture.ai": "cyfuture",
    "Latitude.sh": "latitude-sh",
    "AWS": "aws",
    "Hyperstack": "hyperstack",
    "CCIR": "ccir",
}


@dataclass(frozen=True, slots=True)
class Provider:
    provider_id: str
    provider_name: str
    website: str
    country: str
    region: str
    supplier_type: str
    confidence: str
    updated_at: str
    existing: bool


NEW_PROVIDERS = {
    "kalshi": Provider(
        "kalshi",
        "Kalshi",
        "https://kalshi.com",
        "US",
        "North America",
        "Serverless",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "ornn": Provider(
        "ornn",
        "Ornn",
        "https://data.ornn.com",
        "US",
        "North America",
        "Serverless",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "silicondata": Provider(
        "silicondata",
        "Silicon Data",
        "https://www.silicondata.com",
        "US",
        "North America",
        "GPU Cloud",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "getdeploying": Provider(
        "getdeploying",
        "GetDeploying",
        "https://getdeploying.com",
        "DE",
        "Europe",
        "Serverless",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "deepinfra": Provider(
        "deepinfra",
        "DeepInfra",
        "https://deepinfra.com",
        "US",
        "North America",
        "GPU Cloud",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "fireworks-ai": Provider(
        "fireworks-ai",
        "Fireworks AI",
        "https://fireworks.ai",
        "US",
        "North America",
        "GPU Cloud",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "astra-intellectus": Provider(
        "astra-intellectus",
        "Astra Intellectus",
        "https://astra-intellectus.com",
        "MY",
        "Asia-Pacific",
        "GPU Cloud",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
    "ccir": Provider(
        "ccir",
        "CCIR",
        "https://ccir.io",
        "US",
        "North America",
        "Serverless",
        "review",
        "2026-11-03 00:00:00",
        False,
    ),
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ")
    return str(value).strip()


def _load_sheet(
    workbook_path: Path,
    sheet_name: str,
) -> list[dict[str, str]]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    sheet = workbook[sheet_name]
    rows = sheet.iter_rows(values_only=True)
    headers = [_clean(value) for value in next(rows)]
    result = [
        {header: _clean(value) for header, value in zip(headers, row) if header}
        for row in rows
    ]
    workbook.close()
    return result


def load_provider_dimension(workbook_path: Path) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    for row in _load_sheet(workbook_path, "字典供应商-dim_provider"):
        provider_id = row.get("provider_id", "")
        if not provider_id:
            continue
        providers[provider_id] = Provider(
            provider_id=provider_id,
            provider_name=row.get("provider_name", ""),
            website=row.get("website", ""),
            country=row.get("region_or_hq_country", ""),
            region=row.get("provider_hq_region", ""),
            supplier_type=row.get("supplier_type", ""),
            confidence=row.get("tier_confidence", ""),
            updated_at=row.get("updated_at", ""),
            existing=True,
        )
    return providers


def validate_gpu_dimension(workbook_path: Path) -> None:
    existing = {
        row.get("gpu_id", "") for row in _load_sheet(workbook_path, "字典卡型-dim_gpu")
    }
    missing = sorted(set(GPU_IDS.values()) - existing)
    if missing:
        raise ValueError(f"GPU dimension is missing IDs: {missing}")


def load_history(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"History input is empty: {path}")
    if list(rows[0]) != DETAIL_COLUMNS:
        raise ValueError(f"History columns do not match detail table: {list(rows[0])}")
    if any(row["source_label"] != "price_mining" for row in rows):
        raise ValueError("History contains a source_label other than price_mining")
    return rows


def reconcile_detail(
    rows: list[dict[str, str]],
    existing: dict[str, Provider],
) -> tuple[list[dict[str, str]], list[Provider], list[tuple[str, str, str]]]:
    providers = {**existing, **NEW_PROVIDERS}
    inserts: dict[str, Provider] = {}
    merged: dict[tuple[str, str, str], None] = {}
    output: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        publisher = row["publisher_name"]
        canonical_id = PROVIDER_IDS.get(publisher)
        if canonical_id is None:
            raise ValueError(f"No provider mapping for {publisher!r}")
        provider = providers.get(canonical_id)
        if provider is None:
            raise ValueError(
                f"No provider dimension metadata for {publisher!r} ({canonical_id})"
            )
        old_id = row["provider_id"]
        if old_id != canonical_id:
            merged[(publisher, old_id, canonical_id)] = None
        row["provider_id"] = canonical_id
        row["publisher_name"] = provider.provider_name
        if not row["billing_type"]:
            row["billing_type"] = "SPOT"
        row["supplier_type"] = provider.supplier_type
        if not row["region_or_hq_country"]:
            row["region_or_hq_country"] = provider.country
        if not row["provider_hq_region"]:
            row["provider_hq_region"] = provider.region
        try:
            row["gpu_id"] = GPU_IDS[row["gpu_model_code"]]
        except KeyError as exc:
            raise ValueError(
                f"No GPU dimension mapping for {row['gpu_model_code']!r}"
            ) from exc
        row["record_id"] = make_record_id(
            price_date=row["price_date"],
            run_date=row["run_date"],
            source_label=row["source_label"],
            provider=row["provider_id"],
            region_or_hq_country=(row["region_or_hq_country"] or None),
            provider_hq_region=row["provider_hq_region"] or None,
            gpu_id=row["gpu_id"] or None,
            billing=row["billing_type"] or None,
            term_month=row["term_months"] or None,
            raw_price=row["raw_price"] or None,
            price_gpu_hour=row["price_gpu_hour"] or None,
            availability=row["availability"],
        )
        if not provider.existing:
            inserts[canonical_id] = provider
        output.append(row)
    return output, sorted(inserts.values(), key=lambda p: p.provider_id), sorted(merged)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _percentile(values: list[Decimal], quantile: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def aggregate_provider_series(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if not row["price_gpu_hour"] or not row["term_months"]:
            continue
        key = (
            row["price_date"],
            row["gpu_model_code"],
            row["billing_type"],
            row["term_months"],
            row["provider_id"],
        )
        groups[key].append(row)

    output: list[dict[str, str]] = []
    for key, members in sorted(groups.items()):
        price_date, model, billing, term, provider_id = key
        prices = [Decimal(row["price_gpu_hour"]) for row in members]
        output.append(
            {
                "price_date": price_date,
                "run_date": max(row["run_date"] for row in members),
                "gpu_id": GPU_IDS[model],
                "gpu_model_code": model,
                "billing_type": billing,
                "term_months": term,
                "provider_id": provider_id,
                "median_price": _number(_median(prices)),
                "offering_count": str(len(prices)),
                "supplier_type": members[0]["supplier_type"],
                "reference_url": min(
                    row["source_url"] for row in members if row["source_url"]
                ),
                "source_label": "price_mining",
            }
        )
    return output


def aggregate_price_series(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if not row["price_gpu_hour"] or not row["term_months"]:
            continue
        key = (
            row["price_date"],
            row["gpu_model_code"],
            row["billing_type"],
            row["term_months"],
            row["supplier_type"],
            row["provider_hq_region"],
        )
        groups[key].append(row)

    output: list[dict[str, str]] = []
    for key, members in sorted(groups.items()):
        price_date, model, billing, term, supplier_type, region = key
        prices = [Decimal(row["price_gpu_hour"]) for row in members]
        output.append(
            {
                "price_date": price_date,
                "run_date": max(row["run_date"] for row in members),
                "gpu_id": GPU_IDS[model],
                "gpu_model_code": model,
                "billing_type": billing,
                "term_months": term,
                "supplier_type": supplier_type,
                "region_group": region,
                "median_price": _number(_percentile(prices, Decimal("0.5"))),
                "p25_price": _number(_percentile(prices, Decimal("0.25"))),
                "p75_price": _number(_percentile(prices, Decimal("0.75"))),
                "min_price": _number(min(prices)),
                "offering_count": str(len(prices)),
                "source_label": "price_mining",
            }
        )
    return output


def write_csv(
    path: Path,
    columns: list[str],
    rows: Iterable[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _sql_value(column: str, value: str) -> str:
    if not value:
        return "NULL"
    numeric = {
        "gpu_count",
        "vram_per_gpu_gb",
        "vram_total_gb",
        "cpu_cores",
        "system_ram_gb",
        "disk_storage_gb",
        "interconnect_bandwidth_gbps",
        "gpu_mem_bandwidth_gbps",
        "term_months",
        "raw_price",
        "price_gpu_hour",
        "median_price",
        "offering_count",
        "p25_price",
        "p75_price",
        "min_price",
    }
    if column in numeric:
        Decimal(value)
        return value
    return "'" + value.replace("'", "''") + "'"


def render_insert_sql(
    *,
    table: str,
    columns: list[str],
    rows: list[dict[str, str]],
    start_date: str,
    end_date: str,
) -> str:
    column_sql = ",".join(columns)
    chunks: list[str] = [
        "BEGIN;",
        f"DELETE FROM {table} "
        f"WHERE source_label = 'price_mining' "
        f"AND price_date BETWEEN '{start_date}' AND '{end_date}';",
    ]
    for start in range(0, len(rows), 500):
        batch = rows[start : start + 500]
        values = ",\n".join(
            "    ("
            + ",".join(_sql_value(column, row[column]) for column in columns)
            + ")"
            for row in batch
        )
        chunks.append(f"INSERT INTO {table} ({column_sql}) VALUES\n{values};")
    chunks.append("COMMIT;")
    return "\n\n".join(chunks) + "\n"


def render_provider_insert(providers: list[Provider]) -> str:
    if not providers:
        return "-- No new providers to insert.\n"
    values = ",\n".join(
        "    ("
        + ",".join(
            [
                _sql_value("provider_id", provider.provider_id),
                _sql_value("provider_name", provider.provider_name),
                _sql_value("website", provider.website),
                _sql_value("region_or_hq_country", provider.country),
                _sql_value("provider_hq_region", provider.region),
                _sql_value("supplier_type", provider.supplier_type),
                _sql_value("tier_confidence", provider.confidence),
                _sql_value("updated_at", provider.updated_at),
            ]
        )
        + ")"
        for provider in providers
    )
    columns = ",".join(DIM_PROVIDER_COLUMNS)
    return f"""INSERT INTO {DIM_PROVIDER_TABLE} ({columns})
SELECT
    v.provider_id,
    v.provider_name,
    v.website,
    v.region_or_hq_country,
    v.provider_hq_region,
    v.supplier_type,
    v.tier_confidence,
    v.updated_at::timestamp without time zone
FROM (VALUES
{values}
) AS v ({columns})
WHERE NOT EXISTS (
    SELECT 1
    FROM {DIM_PROVIDER_TABLE} AS existing
    WHERE existing.provider_id = v.provider_id
);
"""


def write_report(
    path: Path,
    *,
    merged: list[tuple[str, str, str]],
    inserted: list[Provider],
    detail_rows: list[dict[str, str]],
    provider_rows: list[dict[str, str]],
    price_rows: list[dict[str, str]],
) -> None:
    duplicate_ids = len(detail_rows) - len({row["record_id"] for row in detail_rows})
    lines = [
        "# Price mining warehouse reconciliation",
        "",
        "## Provider IDs merged",
        "",
    ]
    lines.extend(
        f"- `{publisher}`: `{old_id}` → `{new_id}`"
        for publisher, old_id, new_id in merged
    )
    lines.extend(["", "## Providers inserted into dim_provider", ""])
    lines.extend(
        f"- `{provider.provider_id}` — {provider.provider_name}; "
        f"{provider.country}/{provider.region}; {provider.supplier_type}"
        for provider in inserted
    )
    lines.extend(
        [
            "",
            "## Main transformations",
            "",
            "- Raw price-mining rows are loaded into "
            "`compute_insight_gpu_price_detail_daily`; this follows the workbook "
            "schema (the request had the raw/aggregate table names reversed).",
            "- Existing dim_provider IDs, names, supplier types, and missing HQ "
            "geography are applied before aggregation.",
            "- Blank index-series billing types are normalized to `SPOT`, the "
            "non-null warehouse category for market/index rates.",
            "- Aggregate tables include only priced records with a nonblank term.",
            "- Provider medians group by date, GPU model, provider, billing type, "
            "and term.",
            "- Price percentiles group by date, GPU model, billing type, term, "
            "supplier type, and region.",
            "- Percentile fields use continuous p25/p50/p75; `min_price` is the "
            "minimum (p0), matching the target schema.",
            f"- Detail rows: {len(detail_rows):,}.",
            f"- Provider-series rows: {len(provider_rows):,}.",
            f"- Price-series rows: {len(price_rows):,}.",
            f"- Duplicate record IDs under the requested MD5 formula: "
            f"{duplicate_ids:,}.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile price-mining data and generate warehouse loads."
    )
    parser.add_argument(
        "--history-csv",
        type=Path,
        default=Path("output/gpu_prices_history_20261001_20261103.csv"),
    )
    parser.add_argument(
        "--tables-workbook",
        type=Path,
        default=Path("tables.xlsx"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/warehouse"),
    )
    parser.add_argument(
        "--sql-dir",
        type=Path,
        default=Path("sql/warehouse"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    history = load_history(args.history_csv)
    validate_gpu_dimension(args.tables_workbook)
    existing = load_provider_dimension(args.tables_workbook)
    detail, inserted, merged = reconcile_detail(history, existing)
    provider_series = aggregate_provider_series(detail)
    price_series = aggregate_price_series(detail)
    start_date = min(row["price_date"] for row in detail)
    end_date = max(row["price_date"] for row in detail)

    detail_csv = args.output_dir / "compute_insight_gpu_price_detail_daily.csv"
    provider_csv = args.output_dir / "compute_insight_gpu_provider_series_daily.csv"
    price_csv = args.output_dir / "compute_insight_gpu_price_series_daily.csv"
    write_csv(detail_csv, DETAIL_COLUMNS, detail)
    write_csv(provider_csv, PROVIDER_SERIES_COLUMNS, provider_series)
    write_csv(price_csv, PRICE_SERIES_COLUMNS, price_series)

    args.sql_dir.mkdir(parents=True, exist_ok=True)
    (args.sql_dir / "01_insert_compute_insight_dim_provider.sql").write_text(
        render_provider_insert(inserted),
        encoding="utf-8",
    )
    (args.sql_dir / "02_insert_compute_insight_gpu_price_detail_daily.sql").write_text(
        render_insert_sql(
            table=DETAIL_TABLE,
            columns=DETAIL_COLUMNS,
            rows=detail,
            start_date=start_date,
            end_date=end_date,
        ),
        encoding="utf-8",
    )
    (
        args.sql_dir / "03_insert_compute_insight_gpu_provider_series_daily.sql"
    ).write_text(
        render_insert_sql(
            table=PROVIDER_SERIES_TABLE,
            columns=PROVIDER_SERIES_COLUMNS,
            rows=provider_series,
            start_date=start_date,
            end_date=end_date,
        ),
        encoding="utf-8",
    )
    (args.sql_dir / "04_insert_compute_insight_gpu_price_series_daily.sql").write_text(
        render_insert_sql(
            table=PRICE_SERIES_TABLE,
            columns=PRICE_SERIES_COLUMNS,
            rows=price_series,
            start_date=start_date,
            end_date=end_date,
        ),
        encoding="utf-8",
    )
    write_report(
        args.output_dir / "provider_reconciliation.md",
        merged=merged,
        inserted=inserted,
        detail_rows=detail,
        provider_rows=provider_series,
        price_rows=price_series,
    )

    print(f"Detail rows: {len(detail):,}")
    print(f"Provider-series rows: {len(provider_series):,}")
    print(f"Price-series rows: {len(price_series):,}")
    print(f"New providers: {len(inserted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
