from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from gpu_prices.amd_prices import write_detail_csv
from gpu_prices.workbook import OUTPUT_HEADERS, iso_date, make_record_id


def calendar_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("End date must not be before start date")
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]


def load_detail(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTPUT_HEADERS:
            raise ValueError(f"Unexpected AMD detail columns in {path}")
        return list(reader)


def recompute_record_id(row: dict[str, str]) -> str:
    return make_record_id(
        price_date=row["price_date"],
        run_date=row["run_date"],
        source_label=row["source_label"],
        provider=row["provider_id"],
        region_or_hq_country=row["region_or_hq_country"] or None,
        provider_hq_region=row["provider_hq_region"] or None,
        gpu_id=row["gpu_id"] or None,
        billing=row["billing_type"] or None,
        term_month=row["term_months"] or None,
        raw_price=row["raw_price"] or None,
        price_gpu_hour=row["price_gpu_hour"] or None,
        availability=row["availability"],
    )


def build_history(
    current_rows: list[dict[str, str]],
    *,
    dates: list[date],
    run_date: str,
    fallback_rows: list[dict[str, str]] | None = None,
    fallback_providers: set[str] | None = None,
) -> list[dict[str, str]]:
    end_date = dates[-1].isoformat()
    if any(row["price_date"] != end_date for row in current_rows):
        raise ValueError("Current AMD CSV does not match the requested end date")
    selected = list(current_rows)
    current_providers = {row["provider_id"] for row in current_rows}
    for row in fallback_rows or []:
        if row["provider_id"] not in (fallback_providers or set()):
            continue
        if row["provider_id"] in current_providers:
            continue
        stale = dict(row)
        stale["availability"] = "UNAVAILABLE"
        stale["price_note"] = (
            f"{stale['price_note']} Last known value carried from "
            f"{row['price_date']} because the source was unreachable on {end_date}."
        ).strip()
        selected.append(stale)

    output: list[dict[str, str]] = []
    for day in dates:
        for source in selected:
            row = dict(source)
            row["price_date"] = day.isoformat()
            row["run_date"] = iso_date(run_date)
            row["record_id"] = recompute_record_id(row)
            output.append(row)
    output.sort(
        key=lambda row: (
            row["price_date"],
            row["provider_id"],
            row["gpu_model_code"],
            row["billing_type"],
            int(row["term_months"]),
            row["source_url"],
            row["raw_price"],
        )
    )
    if len({row["record_id"] for row in output}) != len(output):
        raise ValueError("AMD history contains duplicate record IDs")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill AMD provider prices by carrying current static list prices "
            "across the requested date range."
        )
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--current-csv", type=Path, required=True)
    parser.add_argument("--fallback-csv", type=Path)
    parser.add_argument("--fallback-provider", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = datetime.strptime(args.start_date, "%Y%m%d").date()
    end = datetime.strptime(args.end_date, "%Y%m%d").date()
    rows = build_history(
        load_detail(args.current_csv),
        dates=calendar_dates(start, end),
        run_date=args.run_date,
        fallback_rows=(
            load_detail(args.fallback_csv)
            if args.fallback_csv is not None
            else None
        ),
        fallback_providers=set(args.fallback_provider),
    )
    write_detail_csv(args.output, rows)
    print(f"Wrote {len(rows):,} AMD rows across {(end - start).days + 1} dates")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
