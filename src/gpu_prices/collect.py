from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, failed
from gpu_prices.providers import (
    astra_intellectus,
    coreweave,
    daytona,
    deepinfra,
    fireworks_ai,
    getdeploying,
    gpu_ai,
    hyperbolic,
    kalshi,
    nebius,
    ornn,
    runpod,
    silicondata,
    spheron,
    together_ai,
    upcloud,
    verda,
)
from gpu_prices.providers.common import Collector
from gpu_prices.workbook import load_source_rows, write_outputs

REGISTRY: dict[str, Collector] = {
    "Kalshi": kalshi.collect,
    "Ornn": ornn.collect,
    "CoreWeave": coreweave.collect,
    "SiliconData": silicondata.collect,
    "Nebius": nebius.collect,
    "GetDeploying": getdeploying.collect,
    "RunPod": runpod.collect,
    "Together.ai": together_ai.collect,
    "Daytona": daytona.collect,
    "UpCloud": upcloud.collect,
    "Gpu.ai": gpu_ai.collect,
    "Spheron": spheron.collect,
    "Hyperbolic": hyperbolic.collect,
    "DeepInfra": deepinfra.collect,
    "Fireworks.ai": fireworks_ai.collect,
    "Astra Intellectus": astra_intellectus.collect,
    "Verda": verda.collect,
}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _run_provider(
    source_name: str,
    rows: list[SourceRow],
    *,
    now: datetime,
    allow_read_proxy: bool,
) -> list[Observation]:
    collector = REGISTRY[source_name]
    client = HttpClient(allow_read_proxy=allow_read_proxy)
    try:
        observations = collector(rows, client, now)
        expected = {row.workbook_row for row in rows}
        actual = [item.row.workbook_row for item in observations]
        duplicates = [
            row_number for row_number, count in Counter(actual).items() if count > 1
        ]
        missing = sorted(expected - set(actual))
        extra = sorted(set(actual) - expected)
        if duplicates or missing or extra:
            raise ValueError(
                f"collector row mismatch: duplicates={duplicates}, "
                f"missing={missing}, extra={extra}"
            )
        return observations
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return [
            failed(
                row,
                fetched_at=now,
                source_url=row.url,
                note=message,
            )
            for row in rows
        ]


def run(
    *,
    workbook_path: Path,
    output_dir: Path,
    run_date: str,
    providers: list[str] | None,
    workers: int,
    allow_read_proxy: bool,
) -> tuple[list[Observation], tuple[Path, Path, Path]]:
    datetime.strptime(run_date, "%Y%m%d")
    source_rows = load_source_rows(workbook_path)
    by_provider: dict[str, list[SourceRow]] = defaultdict(list)
    for row in source_rows:
        by_provider[row.source_name].append(row)

    unknown = sorted(set(by_provider) - set(REGISTRY))
    if unknown:
        raise ValueError(f"No collector registered for suppliers: {unknown}")
    selected = providers or list(by_provider)
    absent = sorted(set(selected) - set(by_provider))
    if absent:
        raise ValueError(f"Selected suppliers are absent from the workbook: {absent}")

    now = datetime.now(timezone.utc)
    observations: list[Observation] = []
    max_workers = max(1, min(workers, len(selected)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_provider,
                source_name,
                by_provider[source_name],
                now=now,
                allow_read_proxy=allow_read_proxy,
            ): source_name
            for source_name in selected
        }
        for future in as_completed(futures):
            observations.extend(future.result())

    outputs = write_outputs(
        observations,
        run_date=run_date,
        output_dir=output_dir,
    )
    return observations, outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect the GPU prices defined in 算力价格爬虫数据整理.xlsx."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("算力价格爬虫数据整理.xlsx"),
        help="Source workbook path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for CSV, XLSX, and audit output.",
    )
    parser.add_argument(
        "--run-date",
        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
        help="dtstatdate in YYYYMMDD format (default: current UTC date).",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(REGISTRY),
        help="Run only this supplier; repeat to select multiple suppliers.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of suppliers to fetch concurrently (default: 6).",
    )
    parser.add_argument(
        "--allow-read-proxy",
        action="store_true",
        default=_env_flag("GPU_PRICES_ALLOW_READ_PROXY"),
        help=(
            "Allow a public text proxy fallback for sources that block the runner's "
            "IP (Kalshi, GetDeploying, and UpCloud)."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any row has collection status=error.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        observations, outputs = run(
            workbook_path=args.workbook,
            output_dir=args.output_dir,
            run_date=args.run_date,
            providers=args.provider,
            workers=args.workers,
            allow_read_proxy=args.allow_read_proxy,
        )
    except Exception as exc:
        print(f"Collection setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    statuses = Counter(item.status for item in observations)
    print(
        f"Wrote {len(observations)} rows: "
        f"{statuses['ok']} ok, {statuses['unavailable']} unavailable, "
        f"{statuses['error']} errors"
    )
    for path in outputs:
        print(path)
    if args.strict and statuses["error"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
