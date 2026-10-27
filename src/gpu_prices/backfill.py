from __future__ import annotations

import argparse
import bisect
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from gpu_prices.http import HttpClient
from gpu_prices.models import SourceRow
from gpu_prices.providers import kalshi, nebius, silicondata
from gpu_prices.providers.getdeploying import (
    DATASET_URL_TEMPLATE,
    chart_money_2,
    select_reservation_chart_row,
)
from gpu_prices.workbook import OUTPUT_HEADERS, load_source_rows

ORNN_HISTORY_URL = "https://api.ornnai.com/api/gpu/{model}/index-history"
NEBIUS_SERIES_URL = "https://api.nebius.cloud/billing/v1alpha1/spot-price/list-series"
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc

RowKey = tuple[str, str, str, str, str]
History = dict[int, dict[date, Decimal]]


def row_key(row: SourceRow) -> RowKey:
    return (
        row.source_name,
        row.gpu_model_code,
        row.price_type,
        row.region,
        row.cloud_type,
    )


def calendar_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("End date must not be before start date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def parse_utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_current_prices(
    path: Path,
    rows: list[SourceRow],
    end: date,
) -> dict[int, Decimal]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.DictReader(handle))
    expected_date = end.strftime("%Y%m%d")
    by_key: dict[RowKey, Decimal] = {}
    for record in records:
        if record["dtstatdate"] != expected_date:
            raise ValueError(
                f"{path} contains date {record['dtstatdate']}, expected {expected_date}"
            )
        key: RowKey = (
            record["source_name"].strip(),
            record["gpu_model_code"].strip(),
            record["price_type"].strip(),
            record["region"].strip(),
            record["cloud_type"].strip(),
        )
        if key in by_key:
            raise ValueError(f"Duplicate current-price identity in {path}: {key}")
        if not record["price"].strip():
            raise ValueError(f"Current price is blank for {key}")
        by_key[key] = Decimal(record["price"])

    result: dict[int, Decimal] = {}
    for row in rows:
        key = row_key(row)
        if key not in by_key:
            raise ValueError(f"Current-price CSV omitted workbook row {key}")
        result[row.workbook_row] = by_key[key]
    if len(by_key) != len(rows):
        raise ValueError(
            f"Current-price CSV has {len(by_key)} rows; workbook has {len(rows)}"
        )
    return result


def kalshi_history(
    rows: list[SourceRow],
    dates: list[date],
    client: HttpClient,
) -> History:
    result: History = {}
    prefer_proxy = False
    for row in rows:
        curve_url = f"{kalshi.BASE_URL}/{row.gpu_model_code}"
        curve, _, curve_proxied = kalshi._get_json(
            client, curve_url, skip_direct=prefer_proxy
        )
        prefer_proxy = prefer_proxy or curve_proxied
        history, _, history_proxied = kalshi._get_json(
            client,
            f"{curve_url}/history",
            skip_direct=prefer_proxy,
        )
        prefer_proxy = prefer_proxy or history_proxied
        result[row.workbook_row] = {
            day: chart_money_2(
                kalshi.curve_value(
                    curve,
                    history,
                    datetime.combine(
                        day,
                        datetime_time(hour=20),
                        tzinfo=UTC,
                    ),
                )
            )
            for day in dates
        }
    return result


def ornn_history(
    rows: list[SourceRow],
    dates: list[date],
    client: HttpClient,
) -> History:
    wanted = set(dates)
    result: History = {}
    for row in rows:
        url = ORNN_HISTORY_URL.format(model=row.gpu_model_code)
        payload = client.get_json(
            url,
            params={
                "startDate": dates[0].isoformat(),
                "endDate": dates[-1].isoformat(),
            },
        )
        if not payload.get("success"):
            raise ValueError(f"Ornn history failed for {row.gpu_model_code}")
        values: dict[date, Decimal] = {}
        for point in payload.get("data", []):
            settlement_date = parse_utc(point["timestamp"]).astimezone(NEW_YORK).date()
            if settlement_date in wanted:
                values[settlement_date] = Decimal(str(point["index_value"]))
        result[row.workbook_row] = values
    return result


def silicondata_history(
    rows: list[SourceRow],
    dates: list[date],
    client: HttpClient,
) -> History:
    wanted = set(dates)
    result: History = {}
    for row in rows:
        url = silicondata.URL_TEMPLATE.format(model=row.gpu_model_code.lower())
        points: dict[str, Decimal] | None = None
        last_error: ValueError | None = None
        for attempt in range(4):
            html = client.get_text(
                url,
                params={"history_retry": f"{int(time.time())}-{attempt}"},
                headers={"Cache-Control": "no-cache"},
            )
            try:
                points = silicondata.parse_index_history(html)
                break
            except ValueError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.5 * (attempt + 1))
        if points is None:
            raise last_error or ValueError(
                f"Silicon Data history unavailable for {row.gpu_model_code}"
            )
        result[row.workbook_row] = {
            parsed_date: price
            for raw_date, price in points.items()
            if (parsed_date := date.fromisoformat(raw_date)) in wanted
        }
    return result


def _nebius_skus(
    rows: list[SourceRow],
    client: HttpClient,
) -> dict[int, str]:
    items, _ = nebius.fetch_spot_items(client)
    result: dict[int, str] = {}
    for row in rows:
        exact_region = nebius.SPOT_REGIONS[(row.gpu_model_code, row.region)]
        candidates = [
            item
            for item in items
            if item.get("region") == exact_region
            and row.gpu_model_code.lower()
            in item.get("computeInstance", {}).get("platform", "")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one Nebius {row.gpu_model_code} SKU in "
                f"{exact_region}, found {len(candidates)}"
            )
        result[row.workbook_row] = str(candidates[0]["skuId"])
    return result


def _fetch_nebius_points(
    client: HttpClient,
    sku_ids: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, list[tuple[datetime, Decimal]]]:
    result: dict[str, dict[datetime, Decimal]] = {sku_id: {} for sku_id in sku_ids}
    window_start = start
    while window_start < end:
        window_end = min(window_start + timedelta(days=7), end)
        page_token = ""
        while True:
            params: list[tuple[str, object]] = [
                ("filters.startTime", utc_text(window_start)),
                ("filters.endTime", utc_text(window_end)),
                (
                    "aggregation.granularity",
                    "GRANULARITY_MINUTE_15",
                ),
                ("aggregation.method", "METHOD_LAST_PRICE"),
                ("pageSize", 100),
                *(("filters.skuIds", sku_id) for sku_id in sku_ids),
            ]
            if page_token:
                params.append(("pageToken", page_token))
            payload = client.get_json(NEBIUS_SERIES_URL, params=params)
            for series in payload.get("items", []):
                sku_id = str(series["skuId"])
                if sku_id not in result:
                    continue
                for point in series.get("points", []):
                    result[sku_id][parse_utc(point["timestamp"])] = Decimal(
                        point["value"]
                    )
            page_token = payload.get("nextPageToken", "")
            if not page_token:
                break
        window_start = window_end
    return {sku_id: sorted(points.items()) for sku_id, points in result.items()}


def nebius_history(
    rows: list[SourceRow],
    dates: list[date],
    client: HttpClient,
) -> History:
    row_skus = _nebius_skus(rows, client)
    first_midnight = datetime.combine(
        dates[0],
        datetime_time.min,
        tzinfo=UTC,
    )
    final_cutoff = datetime.combine(
        dates[-1],
        datetime_time(hour=21),
        tzinfo=LOS_ANGELES,
    ).astimezone(UTC)
    points = _fetch_nebius_points(
        client,
        sorted(set(row_skus.values())),
        first_midnight,
        final_cutoff,
    )

    result: History = {}
    for row in rows:
        series = points[row_skus[row.workbook_row]]
        timestamps = [point[0] for point in series]
        values: dict[date, Decimal] = {}
        for day in dates:
            cutoff = datetime.combine(
                day,
                datetime_time(hour=21),
                tzinfo=LOS_ANGELES,
            ).astimezone(UTC)
            previous_cutoff = datetime.combine(
                day - timedelta(days=1),
                datetime_time(hour=21),
                tzinfo=LOS_ANGELES,
            ).astimezone(UTC)
            index = bisect.bisect_right(timestamps, cutoff) - 1
            if index >= 0 and series[index][0] > previous_cutoff:
                values[day] = chart_money_2(series[index][1])
        result[row.workbook_row] = values
    return result


def _getdeploying_week_values(
    rows: list[dict[str, str]],
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for price_type, billing_type in (
        ("On-Demand", "ON_DEMAND"),
        ("Spot", "SPOT"),
    ):
        selected = next(
            (
                row
                for row in rows
                if row["billing_type"] == billing_type and row["provider_median_price"]
            ),
            None,
        )
        if selected:
            result[price_type] = chart_money_2(selected["provider_median_price"])
    reservation = select_reservation_chart_row(rows)
    if reservation:
        result["Reserve"] = chart_money_2(reservation["provider_median_price"])
    return result


def getdeploying_history(
    rows: list[SourceRow],
    dates: list[date],
    client: HttpClient,
) -> History:
    result: History = {}
    rows_by_model: dict[str, list[SourceRow]] = defaultdict(list)
    for row in rows:
        rows_by_model[row.gpu_model_code].append(row)

    for model, model_rows in rows_by_model.items():
        url = DATASET_URL_TEMPLATE.format(model=model.lower())
        records = list(csv.DictReader(client.get_text(url).splitlines()))
        by_week: dict[date, list[dict[str, str]]] = defaultdict(list)
        for record in records:
            by_week[date.fromisoformat(record["date"])].append(record)
        weeks = sorted(by_week)
        weekly_values = {
            week: _getdeploying_week_values(by_week[week]) for week in weeks
        }
        for row in model_rows:
            values: dict[date, Decimal] = {}
            for day in dates:
                index = bisect.bisect_right(weeks, day) - 1
                if index >= 0:
                    week = weeks[index]
                    price = weekly_values[week].get(row.price_type)
                    if price is not None:
                        values[day] = price
            result[row.workbook_row] = values
    return result


def build_history(
    rows: list[SourceRow],
    dates: list[date],
    current: dict[int, Decimal],
    client: HttpClient,
) -> tuple[History, set[int]]:
    history: History = {
        row.workbook_row: {day: current[row.workbook_row] for day in dates}
        for row in rows
    }
    curve_rows: set[int] = set()
    groups = {
        "Kalshi": [row for row in rows if row.source_name == "Kalshi"],
        "Ornn": [row for row in rows if row.source_name == "Ornn"],
        "SiliconData": [row for row in rows if row.source_name == "SiliconData"],
        "Nebius": [
            row for row in rows if row.source_name == "Nebius" and row.region != "N/A"
        ],
        "GetDeploying": [row for row in rows if row.source_name == "GetDeploying"],
    }
    collectors = {
        "Kalshi": kalshi_history,
        "Ornn": ornn_history,
        "SiliconData": silicondata_history,
        "Nebius": nebius_history,
        "GetDeploying": getdeploying_history,
    }
    for source_name, source_rows in groups.items():
        values = collectors[source_name](source_rows, dates, client)
        for row in source_rows:
            row_values = values.get(row.workbook_row, {})
            missing = [day for day in dates if day not in row_values]
            if missing:
                raise ValueError(
                    f"{source_name} {row.gpu_model_code} history omitted "
                    f"{', '.join(day.isoformat() for day in missing)}"
                )
            history[row.workbook_row] = row_values
            curve_rows.add(row.workbook_row)
    return history, curve_rows


def write_history_csv(
    path: Path,
    rows: list[SourceRow],
    dates: list[date],
    history: History,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(OUTPUT_HEADERS)
        for day in dates:
            dtstatdate = day.strftime("%Y%m%d")
            for row in sorted(rows, key=lambda item: item.workbook_row):
                writer.writerow(
                    [
                        dtstatdate,
                        row.source_name,
                        row.gpu_model_code,
                        row.price_type,
                        row.region,
                        row.cloud_type,
                        str(history[row.workbook_row][day]),
                    ]
                )


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill daily GPU prices using online history for curve-based "
            "sources and end-date prices for static sources."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("算力价格爬虫数据整理.xlsx"),
    )
    parser.add_argument("--start-date", default="20261001")
    parser.add_argument("--end-date", default="20261026")
    parser.add_argument(
        "--current-csv",
        type=Path,
        help=(
            "Current seven-column price CSV. Defaults to "
            "output/gpu_prices_<end-date>.csv."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Historical output path. Defaults to "
            "output/gpu_prices_history_<start>_<end>.csv."
        ),
    )
    parser.add_argument(
        "--allow-read-proxy",
        action="store_true",
        default=_env_flag("GPU_PRICES_ALLOW_READ_PROXY"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        start = datetime.strptime(args.start_date, "%Y%m%d").date()
        end = datetime.strptime(args.end_date, "%Y%m%d").date()
        dates = calendar_dates(start, end)
        rows = load_source_rows(args.workbook)
        current_csv = args.current_csv or Path(f"output/gpu_prices_{args.end_date}.csv")
        output = args.output or Path(
            f"output/gpu_prices_history_{args.start_date}_{args.end_date}.csv"
        )
        current = load_current_prices(current_csv, rows, end)
        history, curve_rows = build_history(
            rows,
            dates,
            current,
            HttpClient(allow_read_proxy=args.allow_read_proxy),
        )
        write_history_csv(output, rows, dates, history)
    except Exception as exc:
        print(f"Backfill failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        f"Wrote {len(rows) * len(dates)} rows for {len(rows)} prices "
        f"across {len(dates)} dates"
    )
    print(
        f"{len(curve_rows)} curve-based rows used online history; "
        f"{len(rows) - len(curve_rows)} static rows used end-date prices"
    )
    print(output)
    print(
        "Note: Kalshi does not publish archived curve vintages; historical dates "
        "are evaluated on its currently published curve."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
