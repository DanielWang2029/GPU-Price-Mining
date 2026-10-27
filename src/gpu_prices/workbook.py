from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table, TableStyleInfo

from gpu_prices.models import Observation, SourceRow

SOURCE_SHEET = "算力价格来源"
EXPECTED_HEADERS = ["供应商名称", "卡型", "价格类型", "地区", "云类型", "链接", "截图"]
OUTPUT_HEADERS = [
    "dtstatdate",
    "source_name",
    "gpu_model_code",
    "price_type",
    "region",
    "cloud_type",
    "price",
]
AUDIT_HEADERS = [
    "workbook_row",
    *OUTPUT_HEADERS,
    "status",
    "effective_at",
    "fetched_at_utc",
    "source_url",
    "raw_value",
    "note",
]


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def load_source_rows(path: Path) -> list[SourceRow]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    if SOURCE_SHEET not in workbook.sheetnames:
        raise ValueError(f"Workbook is missing sheet {SOURCE_SHEET!r}")
    sheet = workbook[SOURCE_SHEET]
    headers = [_clean(cell.value) for cell in sheet[1]]
    if headers[: len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        raise ValueError(
            f"Unexpected {SOURCE_SHEET!r} headers: {headers[: len(EXPECTED_HEADERS)]}"
        )

    rows: list[SourceRow] = []
    for row_number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=6), start=2):
        values = [_clean(cell.value) for cell in cells]
        if not any(values):
            continue
        if not all(values):
            raise ValueError(
                f"Incomplete source definition at workbook row {row_number}"
            )
        rows.append(
            SourceRow(
                workbook_row=row_number,
                source_name=values[0],
                gpu_model_code=values[1],
                price_type=values[2],
                region=values[3],
                cloud_type=values[4],
                url=values[5],
            )
        )
    workbook.close()
    return rows


def _price_text(observation: Observation) -> str:
    return "" if observation.price is None else str(observation.price)


def _data_row(run_date: str, observation: Observation) -> list[object]:
    row = observation.row
    return [
        run_date,
        row.source_name,
        row.gpu_model_code,
        row.price_type,
        row.region,
        row.cloud_type,
        _price_text(observation),
    ]


def write_outputs(
    observations: Iterable[Observation],
    *,
    run_date: str,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    ordered = sorted(observations, key=lambda item: item.row.workbook_row)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"gpu_prices_{run_date}.csv"
    xlsx_path = output_dir / f"gpu_prices_{run_date}.xlsx"
    audit_path = output_dir / f"gpu_prices_{run_date}_audit.csv"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(OUTPUT_HEADERS)
        for observation in ordered:
            writer.writerow(_data_row(run_date, observation))

    with audit_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(AUDIT_HEADERS)
        for observation in ordered:
            writer.writerow(
                [
                    observation.row.workbook_row,
                    *_data_row(run_date, observation),
                    observation.status,
                    observation.effective_at,
                    observation.fetched_at.isoformat(),
                    observation.source_url,
                    observation.raw_value,
                    observation.note,
                ]
            )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "每日价格"
    sheet.append(OUTPUT_HEADERS)
    for observation in ordered:
        row = _data_row(run_date, observation)
        row[-1] = float(observation.price) if observation.price is not None else None
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    widths = [14, 20, 18, 16, 20, 16, 14]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    table = Table(displayName="DailyGpuPrices", ref=f"A1:G{sheet.max_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)
    workbook.save(xlsx_path)
    return csv_path, xlsx_path, audit_path
