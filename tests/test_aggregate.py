from __future__ import annotations

import unittest

from gpu_prices.aggregate import build_daily_aggregates
from gpu_prices.warehouse import Provider


class DailyAggregateTests(unittest.TestCase):
    def test_daily_aggregates_map_blank_terms_to_na(self) -> None:
        providers = {
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
        base = {
            "price_date": "2026-11-08",
            "run_date": "2026-11-08",
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
            "billing_type": "SPOT",
            "term_months": "",
            "region_or_hq_country": "",
            "provider_hq_region": "",
            "raw_price": "5",
            "price_gpu_hour": "5",
            "availability": "AVAILABLE",
            "price_note": "",
            "source_url": "https://cyfuture.ai/pricing",
        }
        rows = [base, {**base, "billing_type": "RESERVATION", "term_months": "12"}]
        provider_series, price_series = build_daily_aggregates(rows, providers)

        self.assertEqual(
            {row["term_months"] for row in provider_series},
            {"N/A", "12"},
        )
        self.assertEqual(
            {row["term_months"] for row in price_series},
            {"N/A", "12"},
        )
        self.assertTrue(
            all(row["provider_id"] == "cyfuture" for row in provider_series)
        )
        self.assertTrue(all(row["gpu_id"] == "nvidia-b300" for row in price_series))


if __name__ == "__main__":
    unittest.main()
