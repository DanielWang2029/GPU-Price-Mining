from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from gpu_prices.backfill import (
    calendar_dates,
    ccir_history,
    computedesk_history,
    getdeploying_history,
    load_current_prices,
    load_prior_history,
    write_history_csv,
)
from gpu_prices.models import SourceRow
from gpu_prices.workbook import OUTPUT_HEADERS


class TextClient:
    def __init__(self, content: str):
        self.content = content

    def get_text(self, _url: str) -> str:
        return self.content


class JsonClient:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def get_json(self, _url: str) -> dict[str, object]:
        return self.payload


class BackfillTests(unittest.TestCase):
    def test_calendar_range_is_inclusive(self) -> None:
        values = calendar_dates(date(2026, 10, 1), date(2026, 10, 3))
        self.assertEqual(
            values,
            [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)],
        )

    def test_computedesk_carries_latest_business_day_across_weekend(self) -> None:
        source = SourceRow(
            workbook_row=2,
            source_name="Compute Desk",
            supplier_type="Index",
            gpu_model_code="B300",
            price_type="Reserve",
            region="North America",
            term=Decimal("12"),
            url="https://www.computedesk.com/indexes-overview",
        )
        client = JsonClient(
            {
                "indices": [
                    {
                        "alias": "CDB300",
                        "latest_date": "2026-11-06",
                        "latest_value": 7.49,
                        "history": [{"date": "2026-11-06", "value": 7.49}],
                    }
                ]
            }
        )
        dates = calendar_dates(date(2026, 11, 6), date(2026, 11, 8))
        values = computedesk_history([source], dates, client)[2]
        self.assertEqual(
            [values[day] for day in dates],
            [Decimal("7.49"), Decimal("7.49"), Decimal("7.49")],
        )

    def test_ccir_uses_previous_effective_day_and_preserves_gaps(self) -> None:
        source = SourceRow(
            workbook_row=124,
            source_name="CCIR",
            supplier_type="Index",
            gpu_model_code="B300",
            price_type="Spot",
            region="North America",
            url="https://ccir.io/discovery",
        )
        payload = {
            "asof": "2026-10-02",
            "rows": [
                {
                    "id": "b300-northern-virginia-z6",
                    "start": "2026-09-30",
                    "p": [[0, 1.234], [2, 2.345]],
                }
            ],
        }
        client = TextClient(
            f'<script id="disc-data" type="application/json">'
            f"{json.dumps(payload)}</script>"
        )
        dates = calendar_dates(date(2026, 10, 1), date(2026, 10, 3))
        values = ccir_history([source], dates, client)[124]
        self.assertEqual(values[date(2026, 10, 1)], Decimal("1.23"))
        self.assertIsNone(values[date(2026, 10, 2)])
        self.assertEqual(values[date(2026, 10, 3)], Decimal("2.35"))

    def test_getdeploying_forward_fills_weekly_chart_anchors(self) -> None:
        rows = [
            SourceRow(
                workbook_row=22,
                source_name="GetDeploying",
                gpu_model_code="B300",
                price_type="On-Demand",
                region="",
                url="https://getdeploying.com/gpus/nvidia-b300",
            )
        ]
        content = """gpu_slug,date,billing_type,reservation_months,min_price,max_price,median_price,provider_median_price,provider_count,offering_count
nvidia-b300,2026-09-28,ON_DEMAND,,1,10,8.5,8.63,5,10
nvidia-b300,2026-10-05,ON_DEMAND,,1,10,8.7,8.99,5,10
"""
        dates = calendar_dates(date(2026, 10, 1), date(2026, 10, 6))
        result = getdeploying_history(rows, dates, TextClient(content))
        self.assertEqual(result[22][date(2026, 10, 1)], Decimal("8.63"))
        self.assertEqual(result[22][date(2026, 10, 4)], Decimal("8.63"))
        self.assertEqual(result[22][date(2026, 10, 5)], Decimal("8.99"))

    def test_prior_history_accepts_legacy_gpu_id_model_column(self) -> None:
        source = SourceRow(
            workbook_row=7,
            source_name="CoreWeave",
            supplier_type="NeoCloud",
            gpu_model_code="GB200",
            price_type="On-Demand",
            region="North America",
            url="https://www.coreweave.com/pricing",
        )
        legacy_headers = [
            column for column in OUTPUT_HEADERS if column != "gpu_model_code"
        ]
        record = {column: "" for column in legacy_headers}
        record.update(
            {
                "price_date": "2026-10-01",
                "run_date": "2026-10-30",
                "source_label": "price_mining",
                "publisher_name": "CoreWeave",
                "provider_id": "coreweave",
                "supplier_type": "NeoCloud",
                "gpu_id": "GB200",
                "gpu_count": "4",
                "billing_type": "ON_DEMAND",
                "provider_hq_region": "North America",
                "raw_price": "42.00",
                "price_gpu_hour": "10.50",
                "availability": "AVAILABLE",
                "source_url": source.url,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=legacy_headers)
                writer.writeheader()
                writer.writerow(record)
            history = load_prior_history(
                path,
                [source],
                [date(2026, 10, 1)],
            )
        self.assertEqual(
            history[7][date(2026, 10, 1)],
            Decimal("10.50"),
        )

    def test_current_prices_and_history_csv_preserve_schema(self) -> None:
        source = SourceRow(
            workbook_row=7,
            source_name="CoreWeave",
            supplier_type="NeoCloud",
            gpu_model_code="GB200",
            price_type="On-Demand",
            region="North America",
            url="https://www.coreweave.com/pricing",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_path = root / "current.csv"
            current_record = {column: "" for column in OUTPUT_HEADERS}
            current_record.update(
                {
                    "price_date": "2026-10-26",
                    "run_date": "2026-10-30",
                    "source_label": "price_mining",
                    "publisher_name": "CoreWeave",
                    "provider_id": "coreweave",
                    "supplier_type": "NeoCloud",
                    "gpu_id": "",
                    "gpu_model_code": "GB200",
                    "gpu_count": "4",
                    "billing_type": "ON_DEMAND",
                    "provider_hq_region": "North America",
                    "raw_price": "42.00",
                    "price_gpu_hour": "10.50",
                    "availability": "AVAILABLE",
                    "source_url": "https://www.coreweave.com/pricing",
                }
            )
            with current_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS)
                writer.writeheader()
                writer.writerow(current_record)
            current = load_current_prices(
                current_path,
                [source],
                date(2026, 10, 26),
            )
            self.assertEqual(current[7].raw_price, Decimal("42.00"))
            self.assertEqual(current[7].price_gpu_hour, Decimal("10.50"))
            self.assertEqual(current[7].gpu_count, 4)

            output_path = root / "history.csv"
            dates = [date(2026, 10, 25), date(2026, 10, 26)]
            history = {
                7: {
                    date(2026, 10, 25): Decimal("10.50"),
                    date(2026, 10, 26): Decimal("10.50"),
                }
            }
            write_history_csv(
                output_path,
                [source],
                dates,
                history,
                current,
                set(),
                "20261030",
            )
            with output_path.open(encoding="utf-8-sig", newline="") as handle:
                records = list(csv.DictReader(handle))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["price_date"], "2026-10-25")
            self.assertEqual(records[1]["run_date"], "2026-10-30")
            self.assertEqual(records[1]["raw_price"], "42.00")
            self.assertEqual(records[1]["price_gpu_hour"], "10.50")
            self.assertEqual(records[1]["availability"], "AVAILABLE")
            self.assertEqual(records[1]["supplier_type"], "NeoCloud")
            self.assertEqual(records[1]["source_label"], "price_mining")
            self.assertEqual(len(records[1]["record_id"]), 32)
            self.assertEqual(records[1]["gpu_id"], "")
            self.assertEqual(records[1]["gpu_model_code"], "GB200")
            self.assertNotIn("N/A", records[1].values())
            self.assertNotIn(b"\r\n", output_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
