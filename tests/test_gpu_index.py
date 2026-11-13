from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from gpu_prices.gpu_index import (
    PROVIDER_SERIES_COLUMNS,
    SOURCE_LABEL,
    is_gpu_index,
    load_rows,
    rows_from_observations,
    split_detail_rows,
    split_observations,
    write_rows,
)
from gpu_prices.models import SourceRow, ok, unavailable
from gpu_prices.warehouse import NEW_PROVIDERS, PROVIDER_IDS
from gpu_prices.workbook import write_outputs

ROOT = Path(__file__).resolve().parents[1]


class GpuIndexRoutingTests(unittest.TestCase):
    def test_index_values_are_direct_provider_series_rows(self) -> None:
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        sources = [
            SourceRow(
                2,
                "Compute Desk",
                "B300",
                "Reserve",
                "North America",
                "https://www.computedesk.com/indexes-overview",
                "Index",
                Decimal("12"),
            ),
            SourceRow(
                3,
                "Ornn",
                "B200",
                "",
                "",
                "https://data.ornn.com/",
                "Index",
            ),
            SourceRow(
                4,
                "SiliconData",
                "H200",
                "",
                "",
                "https://www.silicondata.com/products/silicon-index/h200",
                "NeoCloud",
            ),
        ]
        observations = [
            ok(
                source,
                price,
                fetched_at=now,
                source_url=source.url,
            )
            for source, price in zip(
                sources,
                [Decimal("7.49"), Decimal("9.88"), Decimal("3.48")],
            )
        ]
        observations.append(
            unavailable(
                sources[0],
                fetched_at=now,
                source_url=sources[0].url,
                note="not published",
            )
        )
        regular_source = SourceRow(
            5,
            "CoreWeave",
            "B200",
            "On-Demand",
            "North America",
            "https://www.coreweave.com/pricing",
            "NeoCloud",
        )
        observations.append(
            ok(
                regular_source,
                Decimal("8.60"),
                fetched_at=now,
                source_url=regular_source.url,
            )
        )

        rows = rows_from_observations(
            observations,
            price_date="2026-11-12",
            run_date="2026-11-12",
        )
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["source_label"] == SOURCE_LABEL for row in rows))
        self.assertTrue(all(row["billing_type"] == "ON_DEMAND" for row in rows))
        self.assertTrue(all(row["term_months"] == "0" for row in rows))
        self.assertTrue(all(row["offering_count"] == "1" for row in rows))
        self.assertEqual(
            {row["provider_id"] for row in rows},
            {"compute-desk", "ornn", "silicondata"},
        )
        self.assertEqual(
            next(row for row in rows if row["provider_id"] == "compute-desk")[
                "median_price"
            ],
            "7.49",
        )
        detail_observations, index_observations = split_observations(observations)
        self.assertEqual(
            [item.row.source_name for item in detail_observations],
            ["CoreWeave"],
        )
        self.assertEqual(len(index_observations), 4)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path, _, audit_path = write_outputs(
                detail_observations,
                price_date="2026-11-12",
                run_date="2026-11-12",
                output_dir=root,
                audit_observations=observations,
            )
            with raw_path.open(encoding="utf-8-sig", newline="") as handle:
                raw_rows = list(csv.DictReader(handle))
            with audit_path.open(encoding="utf-8-sig", newline="") as handle:
                audit_rows = list(csv.DictReader(handle))
            path = root / "gpu-index.csv"
            write_rows(path, rows)
            loaded = load_rows(path)
        self.assertEqual(
            [row["publisher_name"] for row in raw_rows],
            ["CoreWeave"],
        )
        self.assertEqual(len(audit_rows), 5)
        self.assertIn("Silicon Data", {row["publisher_name"] for row in audit_rows})
        self.assertNotIn("SiliconData", {row["publisher_name"] for row in audit_rows})
        self.assertEqual(loaded, rows)
        self.assertEqual(list(loaded[0]), PROVIDER_SERIES_COLUMNS)

    def test_index_providers_are_removed_from_detail_routing(self) -> None:
        rows = [
            {"publisher_name": "CoreWeave", "provider_id": "coreweave"},
            {"publisher_name": "Silicon Data", "provider_id": "silicondata"},
            {"publisher_name": "Ornn", "provider_id": "ornn"},
            {"publisher_name": "Compute Desk", "provider_id": "compute-desk"},
        ]
        detail, index = split_detail_rows(rows)
        self.assertEqual(
            [row["provider_id"] for row in detail],
            ["coreweave"],
        )
        self.assertEqual(
            {row["provider_id"] for row in index},
            {"silicondata", "ornn", "compute-desk"},
        )
        self.assertTrue(is_gpu_index(provider_id="computedesk"))

    def test_cleanup_sql_preserves_gpu_index_rows(self) -> None:
        for filename in (
            "06_delete_legacy_gpu_index_price_detail_daily.sql",
            "07_delete_legacy_gpu_index_provider_series_daily.sql",
        ):
            sql = (ROOT / "sql" / "warehouse" / filename).read_text(
                encoding="utf-8"
            )
            self.assertIn("source_label = 'price_mining'", sql)
            self.assertNotIn("source_label = 'GPU INDEX'", sql)
            self.assertIn("'silicondata'", sql)
            self.assertIn("'ornn'", sql)
            self.assertIn("'compute-desk'", sql)
            self.assertIn("'computedesk'", sql)

    def test_provider_identity_is_canonical_everywhere(self) -> None:
        self.assertEqual(PROVIDER_IDS["Compute Desk"], "compute-desk")
        self.assertEqual(
            NEW_PROVIDERS["compute-desk"].provider_id,
            "compute-desk",
        )
        migration = (
            ROOT
            / "sql"
            / "warehouse"
            / "08_unify_compute_desk_provider_id.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("SET provider_id = 'compute-desk'", migration)
        self.assertIn("WHERE provider_id = 'computedesk'", migration)
        publisher_migration = (
            ROOT
            / "sql"
            / "warehouse"
            / "09_unify_silicon_data_publisher_name.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("SET publisher_name = 'Silicon Data'", publisher_migration)
        self.assertIn("WHERE publisher_name = 'SiliconData'", publisher_migration)

        for filename in (
            "gpu_prices_20261103.csv",
            "gpu_prices_20261108.csv",
            "gpu_prices_history_20261001_20261108.csv",
        ):
            content = (ROOT / "output" / filename).read_text(
                encoding="utf-8-sig"
            )
            self.assertNotIn(",SiliconData,", content)
            self.assertIn(",Silicon Data,", content)
        for filename in ("gpu_prices_20261103.xlsx", "gpu_prices_20261108.xlsx"):
            workbook = load_workbook(
                ROOT / "output" / filename,
                read_only=True,
                data_only=True,
            )
            sheet = workbook["每日价格"]
            headers = [cell.value for cell in sheet[1]]
            publisher_column = headers.index("publisher_name") + 1
            publishers = {
                sheet.cell(row, publisher_column).value
                for row in range(2, sheet.max_row + 1)
            }
            workbook.close()
            self.assertIn("Silicon Data", publishers)
            self.assertNotIn("SiliconData", publishers)


if __name__ == "__main__":
    unittest.main()
