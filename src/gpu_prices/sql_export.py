from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from gpu_prices.workbook import DATA_SOURCE, OUTPUT_HEADERS

TABLE_NAME = "public.t_gpu_daily_prices"
INTEGER_COLUMNS = {"gpu_count", "term_months"}
NUMBER_COLUMNS = {
    "vram_per_gpu_gb",
    "vram_total_gb",
    "cpu_cores",
    "system_ram_gb",
    "disk_storage_gb",
    "interconnect_bandwidth_gbps",
    "gpu_mem_bandwidth_gbps",
    "raw_price",
    "price_gpu_hour",
}

COLUMN_TYPES = {
    "price_date": "DATE",
    "run_date": "DATE",
    "source_label": "TEXT",
    "record_id": "TEXT",
    "publisher_name": "TEXT",
    "provider_id": "TEXT",
    "supplier_type": "TEXT",
    "gpu_id": "TEXT",
    "gpu_count": "INTEGER",
    "gpu_spec": "TEXT",
    "vram_per_gpu_gb": "DOUBLE PRECISION",
    "vram_total_gb": "DOUBLE PRECISION",
    "cpu_cores": "DOUBLE PRECISION",
    "system_ram_gb": "DOUBLE PRECISION",
    "disk_storage_gb": "DOUBLE PRECISION",
    "interconnect_bandwidth_gbps": "DOUBLE PRECISION",
    "gpu_mem_bandwidth_gbps": "DOUBLE PRECISION",
    "billing_type": "TEXT",
    "term_months": "INTEGER",
    "region_or_hq_country": "TEXT",
    "provider_hq_region": "TEXT",
    "raw_price": "DOUBLE PRECISION",
    "price_gpu_hour": "DOUBLE PRECISION",
    "availability": "TEXT",
    "price_note": "TEXT",
    "source_url": "TEXT",
}


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _value(column: str, value: str) -> str:
    if not value:
        return "NULL"
    if column in INTEGER_COLUMNS:
        number = Decimal(value)
        if number != number.to_integral_value():
            raise ValueError(f"{column} must be an integer, got {value!r}")
        return str(int(number))
    if column in NUMBER_COLUMNS:
        Decimal(value)
        return value
    return _quote(value)


def render_sql(csv_path: Path) -> str:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Historical CSV is empty: {csv_path}")
    if list(rows[0]) != OUTPUT_HEADERS:
        raise ValueError(
            f"Unexpected historical columns: {list(rows[0])}; expected {OUTPUT_HEADERS}"
        )
    if any(row["source_label"] != DATA_SOURCE for row in rows):
        raise ValueError("Historical CSV contains a non-price_mining data source")
    if any(value.strip().upper() == "N/A" for row in rows for value in row.values()):
        raise ValueError("Historical CSV contains an N/A placeholder")

    definitions = ",\n".join(
        f"    {column} {COLUMN_TYPES[column]}" for column in OUTPUT_HEADERS
    )
    columns = ",".join(OUTPUT_HEADERS)
    values = ",\n".join(
        "    ("
        + ",".join(_value(column, row[column]) for column in OUTPUT_HEADERS)
        + ")"
        for row in rows
    )
    return (
        f"CREATE TABLE {TABLE_NAME} (\n{definitions}\n);\n\n"
        f"INSERT INTO {TABLE_NAME} ({columns}) VALUES\n{values};\n"
    )


def write_sql(csv_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_sql(csv_path), encoding="utf-8")
    return output_path
