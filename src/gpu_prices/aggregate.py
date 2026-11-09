from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    detail, _, _ = reconcile_detail(rows, providers)
    start_date = min(row["price_date"] for row in detail)
    aggregate_input = select_incremental_aggregate_rows(
        detail,
        incremental_start=start_date,
    )
    return (
        aggregate_provider_series(aggregate_input),
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
    provider_series, price_series = build_daily_aggregates(rows, providers)
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
