from __future__ import annotations

import argparse
from pathlib import Path

from gpu_prices.gpu_index import (
    merge_rows as merge_provider_rows,
)
from gpu_prices.gpu_index import (
    rows_from_detail as gpu_index_rows_from_detail,
)
from gpu_prices.gpu_index import (
    split_detail_rows,
)
from gpu_prices.warehouse import (
    DETAIL_COLUMNS,
    DETAIL_TABLE,
    PRICE_SERIES_COLUMNS,
    PRICE_SERIES_TABLE,
    PROVIDER_SERIES_COLUMNS,
    PROVIDER_SERIES_TABLE,
    _sql_value,
    aggregate_price_series,
    aggregate_provider_series,
    load_history,
    load_provider_dimension,
    reconcile_detail,
    render_insert_sql,
    validate_gpu_dimension,
    write_csv,
)

AWS_CAPACITY_URL = "https://aws.amazon.com/ec2/capacityblocks/pricing/"


def _insert_batches(
    *,
    table: str,
    columns: list[str],
    rows: list[dict[str, str]],
) -> list[str]:
    column_sql = ",".join(columns)
    chunks: list[str] = []
    for start in range(0, len(rows), 500):
        values = ",\n".join(
            "    ("
            + ",".join(_sql_value(column, row[column]) for column in columns)
            + ")"
            for row in rows[start : start + 500]
        )
        chunks.append(f"INSERT INTO {table} ({column_sql}) VALUES\n{values};")
    return chunks


def render_provider_sql(
    *,
    rows: list[dict[str, str]],
    start_date: str,
    index_start_date: str,
    end_date: str,
) -> str:
    direct_provider_ids = sorted(
        {
            row["provider_id"]
            for row in rows
            if row["source_label"] == "GPU INDEX"
        }
    )
    direct_ids_sql = ",".join(
        _sql_value("provider_id", provider_id)
        for provider_id in direct_provider_ids
    )
    chunks = [
        "BEGIN;",
        (
            f"DELETE FROM {PROVIDER_SERIES_TABLE} "
            "WHERE source_label = 'price_mining' "
            f"AND price_date BETWEEN '{start_date}' AND '{end_date}';"
        ),
        (
            f"DELETE FROM {PROVIDER_SERIES_TABLE} "
            "WHERE source_label = 'GPU INDEX' "
            f"AND provider_id IN ({direct_ids_sql}) "
            f"AND price_date BETWEEN '{index_start_date}' AND '{end_date}';"
        ),
        *_insert_batches(
            table=PROVIDER_SERIES_TABLE,
            columns=PROVIDER_SERIES_COLUMNS,
            rows=rows,
        ),
        "COMMIT;",
    ]
    return "\n\n".join(chunks) + "\n"


def normalize_aws_terms(rows: list[dict[str, str]]) -> None:
    for row in rows:
        if (
            row["provider_id"] == "aws"
            and row["billing_type"] == "RESERVATION"
            and row["source_url"] == AWS_CAPACITY_URL
        ):
            row["term_months"] = "6"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Combine an existing raw window with new standard and AMD history, "
            "then generate source-safe detail and aggregate SQL."
        )
    )
    parser.add_argument("--prior-history", type=Path, required=True)
    parser.add_argument("--standard-history", type=Path, required=True)
    parser.add_argument("--amd-history", type=Path, required=True)
    parser.add_argument("--tables-workbook", type=Path, default=Path("tables.xlsx"))
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--index-start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sql-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prior = [
        row
        for row in load_history(args.prior_history)
        if args.start_date <= row["price_date"] < args.index_start_date
    ]
    standard = load_history(args.standard_history)
    amd = load_history(args.amd_history)
    combined = [*prior, *standard, *amd]
    normalize_aws_terms(combined)

    validate_gpu_dimension(args.tables_workbook)
    providers = load_provider_dimension(args.tables_workbook)
    reconciled, _, _ = reconcile_detail(combined, providers)
    detail, index_detail = split_detail_rows(reconciled)
    price_mining_provider = aggregate_provider_series(detail)
    direct_index = gpu_index_rows_from_detail(index_detail)
    provider_csv_rows = merge_provider_rows(price_mining_provider, direct_index)
    provider_sql_rows = [
        row
        for row in provider_csv_rows
        if row["source_label"] == "price_mining"
        or row["price_date"] >= args.index_start_date
    ]
    price_series = aggregate_price_series(detail)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "compute_insight_gpu_price_detail_daily.csv",
        DETAIL_COLUMNS,
        detail,
    )
    write_csv(
        args.output_dir / "compute_insight_gpu_provider_series_daily.csv",
        PROVIDER_SERIES_COLUMNS,
        provider_csv_rows,
    )
    write_csv(
        args.output_dir / "compute_insight_gpu_price_series_daily.csv",
        PRICE_SERIES_COLUMNS,
        price_series,
    )

    args.sql_dir.mkdir(parents=True, exist_ok=True)
    (
        args.sql_dir / "13_insert_compute_insight_gpu_price_detail_daily.sql"
    ).write_text(
        render_insert_sql(
            table=DETAIL_TABLE,
            columns=DETAIL_COLUMNS,
            rows=detail,
            start_date=args.start_date,
            end_date=args.end_date,
        ),
        encoding="utf-8",
    )
    (
        args.sql_dir / "14_insert_compute_insight_gpu_provider_series_daily.sql"
    ).write_text(
        render_provider_sql(
            rows=provider_sql_rows,
            start_date=args.start_date,
            index_start_date=args.index_start_date,
            end_date=args.end_date,
        ),
        encoding="utf-8",
    )
    (
        args.sql_dir / "15_insert_compute_insight_gpu_price_series_daily.sql"
    ).write_text(
        render_insert_sql(
            table=PRICE_SERIES_TABLE,
            columns=PRICE_SERIES_COLUMNS,
            rows=price_series,
            start_date=args.start_date,
            end_date=args.end_date,
        ),
        encoding="utf-8",
    )
    (args.sql_dir / "README.md").write_text(
        f"""# {args.start_date}–{args.end_date} warehouse load

Run in this order:

1. `../12_insert_amd_gpu_providers.sql`
2. `13_insert_compute_insight_gpu_price_detail_daily.sql`
3. `14_insert_compute_insight_gpu_provider_series_daily.sql`
4. `15_insert_compute_insight_gpu_price_series_daily.sql`

Only `coregpu` and `gpubank` are absent from the supplied provider dimension;
SQL 12 contains only those two IDs.

`price_mining` is replaced from {args.start_date} through {args.end_date}.
`GPU INDEX` is replaced only from {args.index_start_date} through
{args.end_date}, preserving earlier index history. GPUBank's last known prices
are marked unavailable because its source was unreachable at the end date.

Row counts:

- Detail: {len(detail):,}
- Provider series SQL: {len(provider_sql_rows):,}
- Price series: {len(price_series):,}
""",
        encoding="utf-8",
    )

    print(f"Combined raw rows: {len(combined):,}")
    print(f"Detail rows: {len(detail):,}")
    print(f"Provider-series rows: {len(provider_csv_rows):,}")
    print(f"Provider-series SQL rows: {len(provider_sql_rows):,}")
    print(f"Price-series rows: {len(price_series):,}")
    print(args.output_dir)
    print(args.sql_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
