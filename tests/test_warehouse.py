from __future__ import annotations

import unittest
from decimal import Decimal

from gpu_prices.warehouse import (
    Provider,
    _percentile,
    aggregate_price_series,
    aggregate_provider_series,
    reconcile_detail,
    render_provider_insert,
)


class WarehouseTests(unittest.TestCase):
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
            "billing_type": "RESERVATION",
            "term_months": "1",
            "region_or_hq_country": "",
            "provider_hq_region": "",
            "raw_price": "5.99",
            "price_gpu_hour": "5.99",
            "availability": "AVAILABLE",
            "price_note": "",
            "source_url": "https://cyfuture.ai/pricing",
        }
        output, inserted, merged = reconcile_detail([row], existing)
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
        self.assertEqual(len(output[0]["record_id"]), 32)

    def test_daily_aggregations(self) -> None:
        base = {
            "price_date": "2026-10-01",
            "run_date": "2026-11-03",
            "gpu_model_code": "B300",
            "billing_type": "ON_DEMAND",
            "term_months": "",
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
        self.assertEqual(north_america["term_months"], "")

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


if __name__ == "__main__":
    unittest.main()
