from __future__ import annotations

import unittest
from decimal import Decimal

from gpu_prices.warehouse import (
    NEW_PROVIDERS,
    PROVIDER_IDS,
    Provider,
    _percentile,
    aggregate_price_series,
    aggregate_provider_series,
    reconcile_detail,
    render_incremental_aggregate_sql,
    render_provider_insert,
    select_incremental_aggregate_rows,
)


class WarehouseTests(unittest.TestCase):
    def test_retired_kalshi_provider_remains_available_for_history(self) -> None:
        self.assertEqual(PROVIDER_IDS["Kalshi"], "kalshi")
        self.assertEqual(NEW_PROVIDERS["kalshi"].provider_name, "Kalshi")

    def test_percentile_continuous_interpolation(self) -> None:
        values = [Decimal("1"), Decimal("2"), Decimal("5"), Decimal("10")]
        self.assertEqual(_percentile(values, Decimal("0.25")), Decimal("1.75"))
        self.assertEqual(_percentile(values, Decimal("0.5")), Decimal("3.5"))
        self.assertEqual(_percentile(values, Decimal("0.75")), Decimal("6.25"))

    def test_provider_reconciliation_uses_existing_dimension(self) -> None:
        existing = {
            "cyfuture": Provider(
                "cyfuture",
                "Cyfuture AI",
                "https://cyfuture.ai",
                "IN",
                "Asia-Pacific",
                "GPU Cloud",
                "high",
                "2026-10-28 04:00:42",
                True,
            )
        }
        row = {
            "price_date": "2026-10-01",
            "run_date": "2026-11-03",
            "source_label": "price_mining",
            "record_id": "",
            "publisher_name": "Cyfuture.ai",
            "provider_id": "cyfutureai",
            "supplier_type": "NeoCloud",
            "gpu_id": "",
            "gpu_model_code": "B300",
            "gpu_count": "1",
            "gpu_spec": "",
            "vram_per_gpu_gb": "",
            "vram_total_gb": "",
            "cpu_cores": "",
            "system_ram_gb": "",
            "disk_storage_gb": "",
            "interconnect_bandwidth_gbps": "",
            "gpu_mem_bandwidth_gbps": "",
            "billing_type": "",
            "term_months": "1",
            "region_or_hq_country": "",
            "provider_hq_region": "",
            "raw_price": "5.99",
            "price_gpu_hour": "5.99",
            "availability": "AVAILABLE",
            "price_note": "",
            "source_url": "https://cyfuture.ai/pricing",
        }
        second = {**row, "gpu_model_code": "H200"}
        output, inserted, merged = reconcile_detail([row, second], existing)
        self.assertEqual(inserted, [])
        self.assertEqual(
            merged,
            [("Cyfuture.ai", "cyfutureai", "cyfuture")],
        )
        self.assertEqual(output[0]["provider_id"], "cyfuture")
        self.assertEqual(output[0]["publisher_name"], "Cyfuture AI")
        self.assertEqual(output[0]["supplier_type"], "GPU Cloud")
        self.assertEqual(output[0]["region_or_hq_country"], "IN")
        self.assertEqual(output[0]["provider_hq_region"], "Asia-Pacific")
        self.assertEqual(output[0]["billing_type"], "SPOT")
        self.assertEqual(output[0]["gpu_id"], "nvidia-b300")
        self.assertEqual(len(output[0]["record_id"]), 32)
        self.assertEqual(output[1]["gpu_id"], "nvidia-h200")
        self.assertNotEqual(output[0]["record_id"], output[1]["record_id"])

    def test_daily_aggregations(self) -> None:
        base = {
            "price_date": "2026-10-01",
            "run_date": "2026-11-03",
            "gpu_model_code": "B300",
            "billing_type": "ON_DEMAND",
            "term_months": "12",
            "provider_id": "one",
            "supplier_type": "GPU Cloud",
            "provider_hq_region": "North America",
            "source_url": "https://one.example",
            "source_label": "price_mining",
        }
        rows = [
            {**base, "price_gpu_hour": "4"},
            {**base, "price_gpu_hour": "8"},
            {
                **base,
                "provider_id": "two",
                "provider_hq_region": "Europe",
                "source_url": "https://two.example",
                "price_gpu_hour": "10",
            },
            {
                **base,
                "provider_id": "ignored-no-term",
                "term_months": "",
                "price_gpu_hour": "1",
            },
        ]
        provider = aggregate_provider_series(rows)
        self.assertEqual(len(provider), 2)
        first = next(row for row in provider if row["provider_id"] == "one")
        self.assertEqual(first["median_price"], "6")
        self.assertEqual(first["offering_count"], "2")
        self.assertEqual(first["gpu_id"], "nvidia-b300")

        prices = aggregate_price_series(rows)
        self.assertEqual(len(prices), 2)
        north_america = next(
            row for row in prices if row["region_group"] == "North America"
        )
        self.assertEqual(north_america["median_price"], "6")
        self.assertEqual(north_america["p25_price"], "5")
        self.assertEqual(north_america["p75_price"], "7")
        self.assertEqual(north_america["min_price"], "4")
        self.assertEqual(north_america["term_months"], "12")

    def test_provider_insert_casts_updated_at_to_timestamp(self) -> None:
        provider = Provider(
            "example",
            "Example",
            "https://example.com",
            "US",
            "North America",
            "GPU Cloud",
            "review",
            "2026-11-03 00:00:00",
            False,
        )
        sql = render_provider_insert([provider])
        self.assertIn(
            "v.updated_at::timestamp without time zone",
            sql,
        )

    def test_incremental_aggregates_normalize_terms_in_incremental_range(self) -> None:
        rows = [
            {
                "price_date": "2026-10-01",
                "billing_type": "SPOT",
                "term_months": "",
            },
            {
                "price_date": "2026-10-01",
                "billing_type": "RESERVATION",
                "term_months": "12",
            },
            {
                "price_date": "2026-11-04",
                "billing_type": "SPOT",
                "term_months": "",
            },
            {
                "price_date": "2026-11-04",
                "billing_type": "RESERVATION",
                "term_months": "",
            },
            {
                "price_date": "2026-11-04",
                "billing_type": "RESERVATION",
                "term_months": "12.0",
            },
        ]
        selected = select_incremental_aggregate_rows(
            rows,
            incremental_start="2026-11-04",
        )
        self.assertEqual(
            [(row["price_date"], row["term_months"]) for row in selected],
            [
                ("2026-11-04", "0"),
                ("2026-11-04", "-1"),
                ("2026-11-04", "12"),
            ],
        )

        provider_row = {
            "price_date": "2026-10-01",
            "run_date": "2026-11-08",
            "gpu_id": "nvidia-b300",
            "gpu_model_code": "B300",
            "billing_type": "SPOT",
            "term_months": "0",
            "provider_id": "example",
            "median_price": "1",
            "offering_count": "1",
            "supplier_type": "Serverless",
            "reference_url": "https://example.com",
            "source_label": "price_mining",
        }
        sql = render_incremental_aggregate_sql(
            table="public.example",
            columns=list(provider_row),
            rows=[provider_row],
            incremental_start_date="2026-11-04",
            end_date="2026-11-08",
            source_labels=("price_mining", "GPU INDEX"),
        )
        self.assertNotIn("N/A", sql)
        self.assertIn(
            "source_label IN ('price_mining','GPU INDEX')",
            sql,
        )
        self.assertIn("'2026-11-04' AND '2026-11-08'", sql)
        self.assertIn(",'SPOT',0,'example'", sql)


if __name__ == "__main__":
    unittest.main()
