from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from gpu_prices.backfill import (
    calendar_dates,
    getdeploying_history,
    load_current_prices,
    write_history_csv,
)
from gpu_prices.models import SourceRow
from gpu_prices.sql_export import render_sql


class TextClient:
    def __init__(self, content: str):
        self.content = content

    def get_text(self, _url: str) -> str:
        return self.content


class BackfillTests(unittest.TestCase):
    def test_calendar_range_is_inclusive(self) -> None:
        values = calendar_dates(date(2026, 10, 1), date(2026, 10, 3))
        self.assertEqual(
            values,
            [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)],
        )

    def test_getdeploying_forward_fills_weekly_chart_anchors(self) -> None:
        rows = [
            SourceRow(
                workbook_row=22,
                source_name="GetDeploying",
                gpu_model_code="B300",
                price_type="On-Demand",
                region="N/A",
                cloud_type="N/A",
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

    def test_current_prices_and_history_csv_preserve_schema(self) -> None:
        source = SourceRow(
            workbook_row=7,
            source_name="CoreWeave",
            supplier_type="NeoCloud",
            gpu_model_code="GB200",
            price_type="On-Demand",
            region="North America",
            cloud_type="N/A",
            url="https://www.coreweave.com/pricing",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_path = root / "current.csv"
            current_path.write_text(
                "dtstatdate,supplier_name,supplier_type,gpu_model_code,"
                "price_type,region,cloud_type,term,url,price,data_source\n"
                "20261026,CoreWeave,NeoCloud,GB200,On-Demand,North America,"
                "N/A,,https://www.coreweave.com/pricing,42.00,price_mining\n",
                encoding="utf-8",
            )
            current = load_current_prices(
                current_path,
                [source],
                date(2026, 10, 26),
            )
            self.assertEqual(current[7], Decimal("42.00"))

            output_path = root / "history.csv"
            dates = [date(2026, 10, 25), date(2026, 10, 26)]
            history = {
                7: {
                    date(2026, 10, 25): Decimal("42.00"),
                    date(2026, 10, 26): Decimal("42.00"),
                }
            }
            write_history_csv(output_path, [source], dates, history)
            with output_path.open(encoding="utf-8-sig", newline="") as handle:
                records = list(csv.DictReader(handle))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["dtstatdate"], "20261025")
            self.assertEqual(records[1]["price"], "42.00")
            self.assertEqual(records[1]["supplier_type"], "NeoCloud")
            self.assertEqual(records[1]["data_source"], "price_mining")
            self.assertNotIn(b"\r\n", output_path.read_bytes())
            sql = render_sql(output_path)
            self.assertIn("CREATE TABLE public.t_gpu_daily_prices", sql)
            self.assertIn("'CoreWeave','NeoCloud','GB200'", sql)
            self.assertNotIn("COPY ", sql)


if __name__ == "__main__":
    unittest.main()
