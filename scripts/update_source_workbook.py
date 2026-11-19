from __future__ import annotations

import argparse
import csv
import posixpath
import tempfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl.utils import get_column_letter

from gpu_prices.collect import REGISTRY
from gpu_prices.identity import publisher_name

SOURCE_SHEET = "算力价格来源"
COLLECT_TASK = "gpu_prices.collect"
AMD_TASK = "gpu_prices.amd_collect"
TASK_HEADER = "采集任务"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ElementTree.register_namespace("", MAIN_NS)
ElementTree.register_namespace("r", OFFICE_REL_NS)


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t")
        )
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared[int(value.text)]
    return value.text


def _source_sheet_path(archive: ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    targets = {
        node.attrib["Id"]: node.attrib["Target"]
        for node in relationships.findall(
            f"{{{PACKAGE_REL_NS}}}Relationship"
        )
    }
    sheet = next(
        node
        for node in workbook.findall(f".//{{{MAIN_NS}}}sheet")
        if node.attrib["name"] == SOURCE_SHEET
    )
    target = targets[sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]]
    return posixpath.normpath(posixpath.join("xl", target))


def _set_inline_cell(
    row: ElementTree.Element,
    *,
    column: int,
    row_number: int,
    value: str,
    style: str = "6",
) -> None:
    reference = f"{get_column_letter(column)}{row_number}"
    existing = next(
        (
            cell
            for cell in row.findall(f"{{{MAIN_NS}}}c")
            if cell.attrib.get("r") == reference
        ),
        None,
    )
    if existing is not None:
        row.remove(existing)
    if value == "":
        return
    cell = ElementTree.Element(
        f"{{{MAIN_NS}}}c",
        {"r": reference, "s": style, "t": "inlineStr"},
    )
    inline = ElementTree.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ElementTree.SubElement(inline, f"{{{MAIN_NS}}}t")
    text.text = value
    row.append(cell)


def _row_values(
    row: ElementTree.Element,
    shared: list[str],
) -> dict[str, str]:
    return {
        "".join(character for character in cell.attrib["r"] if character.isalpha()):
        _cell_value(cell, shared).strip()
        for cell in row.findall(f"{{{MAIN_NS}}}c")
    }


def _amd_sources(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for record in records:
        key = (
            record["publisher_name"],
            record["supplier_type"],
            record["gpu_model_code"],
            record["billing_type"],
            record["term_months"],
            record["provider_hq_region"],
            record["source_url"],
            record["provider_id"],
        )
        grouped[key].append(record)

    price_types = {
        "ON_DEMAND": "On-Demand",
        "SPOT": "Spot",
        "RESERVATION": "Reserve",
    }
    sources: list[dict[str, str]] = []
    for key, rows in sorted(grouped.items()):
        (
            provider_name,
            supplier_type,
            model,
            billing_type,
            term_months,
            region,
            source_url,
            provider_id,
        ) = key
        terms = "" if term_months in {"0", "-1"} else term_months
        counts = ", ".join(
            sorted({row["gpu_count"] for row in rows}, key=int)
        )
        configurations = "; ".join(
            sorted({row["gpu_spec"] for row in rows if row["gpu_spec"]})
        )
        availability = ", ".join(
            sorted({row["availability"] for row in rows})
        )
        notes = (
            f"Tracked by {AMD_TASK}; provider_id={provider_id}; "
            f"source_label=price_mining; GPU counts={counts}; "
            f"availability={availability}."
        )
        if configurations:
            notes += f" Configurations: {configurations}."
        price_notes = "; ".join(
            sorted({row["price_note"] for row in rows if row["price_note"]})
        )
        if price_notes:
            notes += f" {price_notes}"
        sources.append(
            {
                "A": provider_name,
                "B": supplier_type,
                "C": model,
                "D": price_types[billing_type],
                "E": region,
                "F": terms,
                "G": source_url,
                "H": "",
                "I": notes,
                "J": AMD_TASK,
            }
        )
    return sources


def _h100_source() -> dict[str, str]:
    return {
        "A": "Silicon Data",
        "B": "NeoCloud",
        "C": "H100",
        "D": "",
        "E": "",
        "F": "",
        "G": "https://www.silicondata.com/products/silicon-index/h100",
        "H": "",
        "I": (
            "Daily structured GPU price index. Routes directly to "
            "compute_insight_gpu_provider_series_daily with "
            "source_label=GPU INDEX, billing_type=ON_DEMAND, term_months=0, "
            "provider_id=silicondata. No screenshot supplied."
        ),
        "J": COLLECT_TASK,
    }


def update_workbook(
    workbook_path: Path,
    *,
    amd_csv: Path,
) -> tuple[int, int, int]:
    with ZipFile(workbook_path) as archive:
        shared = _shared_strings(archive)
        source_path = _source_sheet_path(archive)
        worksheet = ElementTree.fromstring(archive.read(source_path))
        table = ElementTree.fromstring(archive.read("xl/tables/table1.xml"))
        original_entries = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
        }

    sheet_data = worksheet.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise ValueError("Source worksheet has no sheetData")
    rows = {
        int(row.attrib["r"]): row
        for row in sheet_data.findall(f"{{{MAIN_NS}}}row")
    }
    header = rows[1]
    _set_inline_cell(
        header,
        column=10,
        row_number=1,
        value=TASK_HEADER,
        style="16",
    )
    header.attrib["spans"] = "1:10"

    active_sources = {publisher_name(name) for name in REGISTRY}
    removed = 0
    owned_rows: list[int] = []
    existing_h100 = False
    for row_number, row in rows.items():
        if row_number == 1:
            continue
        values = _row_values(row, shared)
        task = values.get("J", "")
        if task == AMD_TASK:
            owned_rows.append(row_number)
            continue
        source_name = publisher_name(values.get("A", ""))
        if (
            source_name == "Silicon Data"
            and values.get("C") == "H100"
            and values.get("G")
            == "https://www.silicondata.com/products/silicon-index/h100"
        ):
            existing_h100 = True
            _set_inline_cell(
                row,
                column=10,
                row_number=row_number,
                value=COLLECT_TASK,
            )
            continue
        if source_name and source_name not in active_sources:
            for column in range(1, 11):
                _set_inline_cell(
                    row,
                    column=column,
                    row_number=row_number,
                    value="",
                )
            removed += 1

    additions = _amd_sources(amd_csv)
    if not existing_h100:
        additions.insert(0, _h100_source())

    available_rows = [
        number
        for number in sorted(rows)
        if number > 1
        and (
            number in owned_rows
            or not _row_values(rows[number], shared).get("A")
        )
    ]
    if len(available_rows) < len(additions):
        raise ValueError(
            f"Workbook has {len(available_rows)} blank/managed rows for "
            f"{len(additions)} additions"
        )

    for row_number in owned_rows:
        for column in range(1, 11):
            _set_inline_cell(
                rows[row_number],
                column=column,
                row_number=row_number,
                value="",
            )
    for row_number, source in zip(available_rows, additions):
        row = rows[row_number]
        row.attrib["spans"] = "1:10"
        for column, letter in enumerate("ABCDEFGHIJ", start=1):
            _set_inline_cell(
                row,
                column=column,
                row_number=row_number,
                value=source[letter],
            )
        row[:] = sorted(
            row,
            key=lambda cell: "".join(
                character
                for character in cell.attrib["r"]
                if character.isalpha()
            ),
        )

    dimension = worksheet.find(f"{{{MAIN_NS}}}dimension")
    if dimension is not None:
        dimension.attrib["ref"] = "A1:J211"
    columns = worksheet.find(f"{{{MAIN_NS}}}cols")
    if columns is not None and not any(
        column.attrib.get("min") == "10"
        for column in columns.findall(f"{{{MAIN_NS}}}col")
    ):
        ElementTree.SubElement(
            columns,
            f"{{{MAIN_NS}}}col",
            {"min": "10", "max": "10", "width": "24", "customWidth": "1"},
        )

    table.attrib["ref"] = "A1:J211"
    auto_filter = table.find(f"{{{MAIN_NS}}}autoFilter")
    if auto_filter is not None:
        auto_filter.attrib["ref"] = "A1:J211"
    table_columns = table.find(f"{{{MAIN_NS}}}tableColumns")
    if table_columns is None:
        raise ValueError("Source table has no tableColumns")
    if not any(
        column.attrib.get("name") == TASK_HEADER
        for column in table_columns.findall(f"{{{MAIN_NS}}}tableColumn")
    ):
        table_columns.append(
            ElementTree.Element(
                f"{{{MAIN_NS}}}tableColumn",
                {"id": "10", "name": TASK_HEADER},
            )
        )
    table_columns.attrib["count"] = "10"

    original_entries[source_path] = ElementTree.tostring(
        worksheet,
        encoding="utf-8",
        xml_declaration=True,
    )
    original_entries["xl/tables/table1.xml"] = ElementTree.tostring(
        table,
        encoding="utf-8",
        xml_declaration=True,
    )
    with tempfile.NamedTemporaryFile(
        dir=workbook_path.parent,
        suffix=".xlsx",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as output:
            for filename, content in original_entries.items():
                output.writestr(filename, content)
        temporary_path.replace(workbook_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return removed, len(additions), len(owned_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize the source workbook with active collectors."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("算力价格爬虫数据整理.xlsx"),
    )
    parser.add_argument(
        "--amd-csv",
        type=Path,
        default=Path("output/amd_gpu_prices_20261117.csv"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    removed, added, replaced = update_workbook(
        args.workbook,
        amd_csv=args.amd_csv,
    )
    print(f"Removed inactive source rows: {removed}")
    print(f"Added/synchronized source rows: {added}")
    print(f"Replaced prior managed AMD rows: {replaced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
