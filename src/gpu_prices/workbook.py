from __future__ import annotations

import csv
import posixpath
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree
from zipfile import ZipFile

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from gpu_prices.models import Observation, SourceRow

SOURCE_SHEET = "算力价格来源"
EXPECTED_HEADERS = [
    "供应商名称",
    "供应商类型",
    "卡型",
    "价格类型",
    "地区",
    "租期（月）",
    "价格链接",
    "截图",
    "备注",
]
OUTPUT_HEADERS = [
    "price_date",
    "run_date",
    "source_label",
    "record_id",
    "publisher_name",
    "provider_id",
    "supplier_type",
    "gpu_id",
    "gpu_count",
    "gpu_spec",
    "vram_per_gpu_gb",
    "vram_total_gb",
    "cpu_cores",
    "system_ram_gb",
    "disk_storage_gb",
    "interconnect_bandwidth_gbps",
    "gpu_mem_bandwidth_gbps",
    "billing_type",
    "term_months",
    "region_or_hq_country",
    "provider_hq_region",
    "raw_price",
    "price_gpu_hour",
    "availability",
    "price_note",
    "source_url",
]
DATA_SOURCE = "price_mining"
BILLING_TYPES = {
    "On-Demand": "ON_DEMAND",
    "Reserve": "RESERVATION",
    "Spot": "SPOT",
    "": "",
}
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
    cleaned = "" if value is None else str(value).strip()
    return "" if cleaned.upper() == "N/A" else cleaned


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_COLUMN_RE = re.compile(r"([A-Z]+)")


def _xml_sheet_rows(path: Path, sheet_name: str) -> list[tuple[int, dict[str, str]]]:
    """Read cell values without parsing styles.

    The source workbook contains empty Excel fill records that openpyxl rejects,
    although its worksheet data is valid. Reading the OOXML values directly
    keeps ingestion independent of workbook styling.
    """
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{_MAIN_NS}}}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
                )

        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        relationship_targets = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        }
        sheet_node = next(
            (
                node
                for node in workbook.findall(f".//{{{_MAIN_NS}}}sheet")
                if node.attrib["name"] == sheet_name
            ),
            None,
        )
        if sheet_node is None:
            raise ValueError(f"Workbook is missing sheet {sheet_name!r}")
        relationship_id = sheet_node.attrib[f"{{{_OFFICE_REL_NS}}}id"]
        sheet_path = posixpath.normpath(
            posixpath.join("xl", relationship_targets[relationship_id])
        )
        sheet = ElementTree.fromstring(archive.read(sheet_path))

        rows: list[tuple[int, dict[str, str]]] = []
        for row_node in sheet.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"):
            row_number = int(row_node.attrib["r"])
            values: dict[str, str] = {}
            for cell in row_node.findall(f"{{{_MAIN_NS}}}c"):
                reference = cell.attrib["r"]
                match = _CELL_COLUMN_RE.match(reference)
                if match is None:
                    continue
                column = match.group(1)
                cell_type = cell.attrib.get("t")
                value_node = cell.find(f"{{{_MAIN_NS}}}v")
                if cell_type == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")
                    )
                elif value_node is None or value_node.text is None:
                    value = ""
                elif cell_type == "s":
                    value = shared_strings[int(value_node.text)]
                elif cell_type == "b":
                    value = "TRUE" if value_node.text == "1" else "FALSE"
                else:
                    value = value_node.text
                values[column] = value
            rows.append((row_number, values))
        return rows


def _parse_term(value: str, row_number: int) -> Decimal | None:
    if not value or value.upper() == "N/A":
        return None
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValueError(
            f"Invalid term {value!r} at workbook row {row_number}"
        ) from exc


def load_source_rows(path: Path) -> list[SourceRow]:
    xml_rows = _xml_sheet_rows(path, SOURCE_SHEET)
    first_row = next(
        (values for row_number, values in xml_rows if row_number == 1),
        {},
    )
    headers = [
        _clean(first_row.get(get_column_letter(index), ""))
        for index in range(1, len(EXPECTED_HEADERS) + 1)
    ]
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"Unexpected {SOURCE_SHEET!r} headers: {headers}")

    rows: list[SourceRow] = []
    for row_number, cells in xml_rows:
        if row_number < 2:
            continue
        values = [
            _clean(cells.get(get_column_letter(index), "")) for index in range(1, 8)
        ]
        if not any(values):
            continue
        required = values[:3] + [values[6]]
        if not all(required):
            raise ValueError(
                f"Incomplete source definition at workbook row {row_number}"
            )
        rows.append(
            SourceRow(
                workbook_row=row_number,
                source_name=values[0],
                supplier_type=values[1],
                gpu_model_code=values[2],
                price_type=values[3],
                region=values[4],
                term=_parse_term(values[5], row_number),
                url=values[6],
            )
        )
    return rows


def provider_id(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def billing_type(value: str) -> str:
    try:
        return BILLING_TYPES[value]
    except KeyError as exc:
        raise ValueError(f"Unsupported price type {value!r}") from exc


def iso_date(value: str) -> str:
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    raise ValueError(f"Date must be YYYYMMDD or YYYY-MM-DD, got {value!r}")


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def data_row(
    price_date: str,
    run_date: str,
    observation: Observation,
) -> list[object]:
    return record_row(
        price_date,
        run_date,
        observation.row,
        raw_price=observation.raw_price,
        price_gpu_hour=observation.price_gpu_hour,
        gpu_count=observation.gpu_count,
        availability=observation.availability,
    )


def record_row(
    price_date: str,
    run_date: str,
    row: SourceRow,
    *,
    raw_price: Decimal | None,
    price_gpu_hour: Decimal | None,
    gpu_count: int,
    availability: str,
) -> list[object]:
    return [
        iso_date(price_date),
        iso_date(run_date),
        DATA_SOURCE,
        "",
        row.source_name,
        provider_id(row.source_name),
        row.supplier_type,
        row.gpu_model_code,
        gpu_count,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        billing_type(row.price_type),
        "" if row.term is None else str(row.term),
        "",
        row.region,
        _decimal_text(raw_price),
        _decimal_text(price_gpu_hour),
        availability,
        "",
        row.url,
    ]


def write_outputs(
    observations: Iterable[Observation],
    *,
    price_date: str,
    run_date: str,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    ordered = sorted(observations, key=lambda item: item.row.workbook_row)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_token = iso_date(price_date).replace("-", "")
    csv_path = output_dir / f"gpu_prices_{date_token}.csv"
    xlsx_path = output_dir / f"gpu_prices_{date_token}.xlsx"
    audit_path = output_dir / f"gpu_prices_{date_token}_audit.csv"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(OUTPUT_HEADERS)
        for observation in ordered:
            writer.writerow(data_row(price_date, run_date, observation))

    with audit_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(AUDIT_HEADERS)
        for observation in ordered:
            writer.writerow(
                [
                    observation.row.workbook_row,
                    *data_row(price_date, run_date, observation),
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
        row = data_row(price_date, run_date, observation)
        row[8] = observation.gpu_count
        row[18] = (
            float(observation.row.term) if observation.row.term is not None else None
        )
        row[21] = (
            float(observation.raw_price) if observation.raw_price is not None else None
        )
        row[22] = (
            float(observation.price_gpu_hour)
            if observation.price_gpu_hour is not None
            else None
        )
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    widths = [
        14,
        14,
        16,
        14,
        22,
        18,
        16,
        12,
        12,
        14,
        18,
        16,
        14,
        18,
        18,
        30,
        30,
        16,
        14,
        22,
        22,
        14,
        18,
        16,
        20,
        48,
    ]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    last_column = get_column_letter(len(OUTPUT_HEADERS))
    table = Table(
        displayName="DailyGpuPrices",
        ref=f"A1:{last_column}{sheet.max_row}",
    )
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
