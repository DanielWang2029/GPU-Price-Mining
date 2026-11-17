from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from gpu_prices.amd_prices import (
    AmdOffer,
    build_detail_rows,
    render_detail_sql,
    render_provider_sql,
    write_detail_csv,
)
from gpu_prices.amd_providers import (
    bentaus,
    cirrascale,
    coregpu,
    cyfuture,
    daytona,
    digitalocean,
    gpubank,
    hotaisle,
    impossible_cloud,
    microsoft_azure,
    openrelay,
    oracle_cloud,
    runcrate,
    runpod,
    tensorwave,
    vultr,
)
from gpu_prices.http import HttpClient
from gpu_prices.workbook import iso_date

LOS_ANGELES = ZoneInfo("America/Los_Angeles")
REGISTRY = {
    "Bentaus": bentaus.collect,
    "Cirrascale": cirrascale.collect,
    "CoreGPU": coregpu.collect,
    "Cyfuture AI": cyfuture.collect,
    "Daytona": daytona.collect,
    "DigitalOcean": digitalocean.collect,
    "GPUBank": gpubank.collect,
    "Hot Aisle": hotaisle.collect,
    "Impossible Cloud": impossible_cloud.collect,
    "Microsoft Azure": microsoft_azure.collect,
    "OpenRelay": openrelay.collect,
    "Oracle Cloud": oracle_cloud.collect,
    "Runcrate": runcrate.collect,
    "Runpod": runpod.collect,
    "TensorWave": tensorwave.collect,
    "Vultr": vultr.collect,
}
AUDIT_COLUMNS = ["provider_name", "status", "row_count", "note"]


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _collect_provider(
    provider_name: str,
    *,
    now: datetime,
    allow_read_proxy: bool,
) -> list[AmdOffer]:
    client = HttpClient(allow_read_proxy=allow_read_proxy)
    return REGISTRY[provider_name](client, now)


def run(
    *,
    output_dir: Path,
    sql_dir: Path,
    price_date: str,
    run_date: str,
    providers: list[str] | None,
    workers: int,
    allow_read_proxy: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]], tuple[Path, Path, Path, Path]]:
    price_date = iso_date(price_date)
    run_date = iso_date(run_date)
    selected = providers or list(REGISTRY)
    now = datetime.now(timezone.utc)
    offers: list[AmdOffer] = []
    audit: list[dict[str, str]] = []

    with ThreadPoolExecutor(
        max_workers=max(1, min(workers, len(selected)))
    ) as executor:
        futures = {
            executor.submit(
                _collect_provider,
                provider_name,
                now=now,
                allow_read_proxy=allow_read_proxy,
            ): provider_name
            for provider_name in selected
        }
        for future in as_completed(futures):
            provider_name = futures[future]
            try:
                provider_offers = future.result()
                offers.extend(provider_offers)
                audit.append(
                    {
                        "provider_name": provider_name,
                        "status": "ok",
                        "row_count": str(len(provider_offers)),
                        "note": "",
                    }
                )
            except Exception as exc:
                audit.append(
                    {
                        "provider_name": provider_name,
                        "status": "error",
                        "row_count": "0",
                        "note": f"{type(exc).__name__}: {exc}",
                    }
                )

    rows, duplicates = build_detail_rows(
        offers,
        price_date=price_date,
        run_date=run_date,
    )
    for provider_id, kept_url, dropped_url in duplicates:
        audit.append(
            {
                "provider_name": provider_id,
                "status": "deduplicated",
                "row_count": "0",
                "note": (
                    f"Identical record-ID fields: kept {kept_url}; "
                    f"dropped {dropped_url}."
                ),
            }
        )
    audit.sort(key=lambda row: (row["provider_name"], row["status"]))

    date_token = price_date.replace("-", "")
    csv_path = output_dir / f"amd_gpu_prices_{date_token}.csv"
    audit_path = output_dir / f"amd_gpu_prices_{date_token}_audit.csv"
    detail_sql_path = (
        sql_dir / f"11_insert_amd_gpu_price_detail_daily_{date_token}.sql"
    )
    provider_sql_path = sql_dir / "12_insert_amd_gpu_providers.sql"
    write_detail_csv(csv_path, rows)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=AUDIT_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(audit)
    sql_dir.mkdir(parents=True, exist_ok=True)
    detail_sql_path.write_text(render_detail_sql(rows), encoding="utf-8")
    provider_sql_path.write_text(
        render_provider_sql(
            {row["provider_id"] for row in rows},
            updated_at=f"{run_date} 00:00:00",
        ),
        encoding="utf-8",
    )
    return rows, audit, (csv_path, audit_path, detail_sql_path, provider_sql_path)


def build_parser() -> argparse.ArgumentParser:
    today = datetime.now(LOS_ANGELES).strftime("%Y%m%d")
    parser = argparse.ArgumentParser(
        description="Collect repeatable public AMD Instinct cloud prices."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--sql-dir", type=Path, default=Path("sql/warehouse"))
    parser.add_argument("--price-date", default=today)
    parser.add_argument("--run-date", default=today)
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(REGISTRY),
        help="Run only this provider; repeat to select multiple providers.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--allow-read-proxy",
        action="store_true",
        default=_env_flag("GPU_PRICES_ALLOW_READ_PROXY"),
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows, audit, paths = run(
            output_dir=args.output_dir,
            sql_dir=args.sql_dir,
            price_date=args.price_date,
            run_date=args.run_date,
            providers=args.provider,
            workers=args.workers,
            allow_read_proxy=args.allow_read_proxy,
        )
    except Exception as exc:
        print(f"AMD collection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    errors = [row for row in audit if row["status"] == "error"]
    unavailable = sum(row["availability"] != "AVAILABLE" for row in rows)
    print(
        f"Wrote {len(rows)} AMD price rows: {len(errors)} provider errors, "
        f"{unavailable} unavailable/waitlist rows"
    )
    for path in paths:
        print(path)
    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
