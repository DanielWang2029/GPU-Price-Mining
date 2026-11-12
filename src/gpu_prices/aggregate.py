from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gpu_prices.gpu_index import (
    load_rows as load_gpu_index_rows,
)
from gpu_prices.gpu_index import (
    merge_rows as merge_gpu_index_rows,
)
from gpu_prices.gpu_index import (
    rows_from_detail as gpu_index_rows_from_detail,
)
from gpu_prices.gpu_index import (
    split_detail_rows,
)
from gpu_prices.warehouse import (
    PRICE_SERIES_COLUMNS,
    PROVIDER_SERIES_COLUMNS,
    Provider,
    aggregate_price_series,
    aggregate_provider_series,
    load_history,
    load_provider_dimension,
    reconcile_detail,
    select_incremental_aggregate_rows,
    validate_gpu_dimension,
    write_csv,
)

LOS_ANGELES = ZoneInfo("America/Los_Angeles")


def build_daily_aggregates(
    rows: list[dict[str, str]],
    providers: dict[str, Provider],
    index_rows: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    reconciled, _, _ = reconcile_detail(rows, providers)
    detail, legacy_index_detail = split_detail_rows(reconciled)
    start_date = min(row["price_date"] for row in reconciled)
    aggregate_input = select_incremental_aggregate_rows(
        detail,
        incremental_start=start_date,
    )
    direct_index_rows = merge_gpu_index_rows(
        gpu_index_rows_from_detail(legacy_index_detail),
        index_rows or [],
    )
    provider_rows = [
        *aggregate_provider_series(aggregate_input),
        *direct_index_rows,
    ]
    provider_rows.sort(
        key=lambda row: (
            row["price_date"],
            row["gpu_model_code"],
            row["provider_id"],
            row["billing_type"],
            row["term_months"],
        )
    )
    return (
        provider_rows,
        aggregate_price_series(aggregate_input),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate daily provider and market price aggregates from a raw "
            "price-mining CSV."
        )
    )
    today = datetime.now(LOS_ANGELES).strftime("%Y%m%d")
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path(f"output/gpu_prices_{today}.csv"),
    )
    parser.add_argument(
        "--tables-workbook",
        type=Path,
        default=Path("tables.xlsx"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
    )
    parser.add_argument(
        "--gpu-index-csv",
        type=Path,
        help=(
            "Direct GPU INDEX provider-series CSV emitted by gpu_prices.collect."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = load_history(args.input_csv)
    dates = sorted({row["price_date"] for row in rows})
    if len(dates) != 1:
        raise ValueError(
            f"Daily aggregate input must contain exactly one date, got {dates}"
        )
    validate_gpu_dimension(args.tables_workbook)
    providers = load_provider_dimension(args.tables_workbook)
    index_rows = (
        load_gpu_index_rows(args.gpu_index_csv)
        if args.gpu_index_csv is not None
        else []
    )
    index_dates = {row["price_date"] for row in index_rows}
    if index_dates and index_dates != set(dates):
        raise ValueError(
            f"GPU INDEX dates {sorted(index_dates)} do not match raw dates {dates}"
        )
    provider_series, price_series = build_daily_aggregates(
        rows,
        providers,
        index_rows,
    )
    date_token = dates[0].replace("-", "")

    provider_path = (
        args.output_dir / f"compute_insight_gpu_provider_series_daily_{date_token}.csv"
    )
    price_path = (
        args.output_dir / f"compute_insight_gpu_price_series_daily_{date_token}.csv"
    )
    write_csv(provider_path, PROVIDER_SERIES_COLUMNS, provider_series)
    write_csv(price_path, PRICE_SERIES_COLUMNS, price_series)
    print(f"Provider-series rows: {len(provider_series):,}")
    print(f"Price-series rows: {len(price_series):,}")
    print(provider_path)
    print(price_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
