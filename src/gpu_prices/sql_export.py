from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from gpu_prices.workbook import DATA_SOURCE, OUTPUT_HEADERS

TABLE_NAME = "public.t_gpu_daily_prices"
IDENTITY_COLUMNS = [
    "supplier_name",
    "supplier_type",
    "gpu_model_code",
    "price_type",
    "region",
    "cloud_type",
    "term",
    "url",
    "data_source",
]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _number(value: str) -> str:
    return value if value else "NULL"


def _values(rows: list[tuple[str, ...]], *, price_last: bool = True) -> str:
    rendered: list[str] = []
    for row in rows:
        fields = [_quote(value) for value in row[:-1]]
        fields.append(_number(row[-1]) if price_last else _quote(row[-1]))
        rendered.append("(" + ",".join(fields) + ")")
    return ",".join(rendered)


def render_sql(csv_path: Path) -> str:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Historical CSV is empty: {csv_path}")
    if list(rows[0]) != OUTPUT_HEADERS:
        raise ValueError(
            f"Unexpected historical columns: {list(rows[0])}; expected {OUTPUT_HEADERS}"
        )
    if any(row["data_source"] != DATA_SOURCE for row in rows):
        raise ValueError("Historical CSV contains a non-price_mining data source")

    dates = sorted({row["dtstatdate"] for row in rows})
    by_identity: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        identity = tuple(row[column] for column in IDENTITY_COLUMNS)
        by_identity[identity].append(row)

    static_rows: list[tuple[str, ...]] = []
    curve_rows: list[tuple[str, ...]] = []
    for identity, identity_rows in by_identity.items():
        prices = {row["price"] for row in identity_rows}
        if len(prices) == 1:
            static_rows.append((*identity, next(iter(prices))))
        else:
            curve_rows.extend(
                (
                    row["dtstatdate"],
                    *(row[column] for column in IDENTITY_COLUMNS),
                    row["price"],
                )
                for row in identity_rows
            )
    static_rows.sort()
    curve_rows.sort()

    date_values = ",".join(f"({_quote(value)})" for value in dates)
    return f"""CREATE TABLE {TABLE_NAME} (
    dtstatdate TEXT,
    supplier_name TEXT,
    supplier_type TEXT,
    gpu_model_code TEXT,
    price_type TEXT,
    region TEXT,
    cloud_type TEXT,
    term DOUBLE PRECISION,
    url TEXT,
    price DOUBLE PRECISION,
    data_source TEXT
);

WITH dates(dtstatdate) AS (VALUES {date_values}),
static_prices(supplier_name,supplier_type,gpu_model_code,price_type,region,cloud_type,term,url,data_source,price) AS (VALUES {_values(static_rows)}),
curve_prices(dtstatdate,supplier_name,supplier_type,gpu_model_code,price_type,region,cloud_type,term,url,data_source,price) AS (VALUES {_values(curve_rows)})
INSERT INTO {TABLE_NAME} (dtstatdate,supplier_name,supplier_type,gpu_model_code,price_type,region,cloud_type,term,url,price,data_source)
SELECT d.dtstatdate,s.supplier_name,s.supplier_type,s.gpu_model_code,s.price_type,s.region,s.cloud_type,NULLIF(s.term,'')::DOUBLE PRECISION,s.url,s.price,s.data_source
FROM dates AS d CROSS JOIN static_prices AS s
UNION ALL
SELECT dtstatdate,supplier_name,supplier_type,gpu_model_code,price_type,region,cloud_type,NULLIF(term,'')::DOUBLE PRECISION,url,price,data_source
FROM curve_prices;
"""


def write_sql(csv_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_sql(csv_path), encoding="utf-8")
    return output_path
