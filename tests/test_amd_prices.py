from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from gpu_prices.amd_backfill import build_history
from gpu_prices.amd_prices import (
    AmdOffer,
    build_detail_rows,
    detail_row,
    render_detail_sql,
    render_provider_sql,
)
from gpu_prices.amd_providers.cirrascale import parse_price_card
from gpu_prices.amd_providers.digitalocean import parse_docs_prices
from gpu_prices.amd_providers.hotaisle import parse_prices as parse_hotaisle_prices
from gpu_prices.amd_providers.tensorwave import parse_price as parse_tensorwave_price
from gpu_prices.providers.bentaus import parse_ranges


class AmdPriceTests(unittest.TestCase):
    def test_static_backfill_carries_current_and_explicit_fallback_prices(self) -> None:
        current = detail_row(
            AmdOffer(
                provider_id="openrelay",
                gpu_model_code="MI300X",
                billing_type="ON_DEMAND",
                term_months=0,
                raw_price=Decimal("1.99"),
                price_gpu_hour=Decimal("1.99"),
                gpu_count=1,
                availability="AVAILABLE",
                source_url="https://api.openrelay.inc/v1/public/pricing",
            ),
            price_date="2026-11-19",
            run_date="2026-11-19",
        )
        fallback = detail_row(
            AmdOffer(
                provider_id="gpubank",
                gpu_model_code="MI300X",
                billing_type="ON_DEMAND",
                term_months=0,
                raw_price=Decimal("1.65"),
                price_gpu_hour=Decimal("1.65"),
                gpu_count=1,
                availability="AVAILABLE",
                source_url="https://gpubank.io/prices.json",
            ),
            price_date="2026-11-17",
            run_date="2026-11-17",
        )
        rows = build_history(
            [current],
            dates=[date(2026, 11, 18), date(2026, 11, 19)],
            run_date="20261119",
            fallback_rows=[fallback],
            fallback_providers={"gpubank"},
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["record_id"] for row in rows}), 4)
        gpubank = [row for row in rows if row["provider_id"] == "gpubank"]
        self.assertTrue(all(row["availability"] == "UNAVAILABLE" for row in gpubank))
        self.assertTrue(all("Last known value" in row["price_note"] for row in gpubank))

    def test_detail_rows_and_sql_use_amd_dimensions(self) -> None:
        offer = AmdOffer(
            provider_id="digitalocean",
            gpu_model_code="MI355X",
            billing_type="SPOT",
            term_months=0,
            raw_price=Decimal("36"),
            price_gpu_hour=Decimal("4.50"),
            gpu_count=8,
            availability="AVAILABLE",
            source_url="https://docs.digitalocean.com/pricing",
            gpu_spec="gpu-mi355x8-2304gb-spot",
        )
        rows, duplicates = build_detail_rows(
            [offer],
            price_date="2026-11-17",
            run_date="2026-11-17",
        )
        self.assertEqual(duplicates, [])
        self.assertEqual(rows[0]["gpu_id"], "amd-mi355x")
        self.assertEqual(rows[0]["vram_per_gpu_gb"], "288")
        self.assertEqual(rows[0]["vram_total_gb"], "2304")
        self.assertEqual(rows[0]["raw_price"], "36")
        self.assertEqual(rows[0]["price_gpu_hour"], "4.5")
        self.assertEqual(len(rows[0]["record_id"]), 32)

        sql = render_detail_sql(rows)
        self.assertIn(
            "INSERT INTO public.compute_insight_gpu_price_detail_daily",
            sql,
        )
        self.assertNotIn("public.public.", sql)
        self.assertIn("'digitalocean'", sql)
        self.assertIn("'amd-mi355x'", sql)

    def test_identical_sources_are_deduplicated_by_record_id(self) -> None:
        base = {
            "provider_id": "digitalocean",
            "gpu_model_code": "MI300X",
            "billing_type": "ON_DEMAND",
            "term_months": 0,
            "raw_price": Decimal("2.59"),
            "price_gpu_hour": Decimal("2.59"),
            "gpu_count": 1,
            "availability": "AVAILABLE",
        }
        rows, duplicates = build_detail_rows(
            [
                AmdOffer(**base, source_url="https://one.example"),
                AmdOffer(**base, source_url="https://two.example"),
            ],
            price_date="2026-11-17",
            run_date="2026-11-17",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            duplicates,
            [("digitalocean", "https://one.example", "https://two.example")],
        )

    def test_provider_sql_is_idempotent(self) -> None:
        sql = render_provider_sql(
            ["digitalocean", "openrelay", "coregpu", "gpubank"],
            updated_at="2026-11-17 00:00:00",
            existing_provider_ids={"digitalocean", "openrelay"},
        )
        self.assertIn("WHERE NOT EXISTS", sql)
        self.assertNotIn("'OpenRelay'", sql)
        self.assertNotIn("'DigitalOcean'", sql)
        self.assertIn("'CoreGPU'", sql)
        self.assertIn("'GPUBank'", sql)
        self.assertIn("'Unclassified'", sql)
        self.assertIn("'Unknown','Other','Unclassified'", sql)
        self.assertIn("WHERE provider_id = 'gpubank'", sql)
        self.assertIn("NULLIF(provider_hq_region, '')", sql)
        self.assertIn("::timestamp without time zone", sql)

    def test_provider_page_parsers(self) -> None:
        digitalocean = parse_docs_prices(
            """
            <h2>On-Demand GPU Droplet Pricing</h2>
            <table><tr><td>AMD MI300X (8x)</td><td>$20.72 per hour</td></tr></table>
            <h2>Spot GPU Droplet Pricing public</h2>
            <table><tr><td>AMD MI355X (8x)</td><td>$36.00 per hour</td></tr></table>
            """
        )
        self.assertEqual(
            digitalocean[("MI300X", "ON_DEMAND", 8)],
            Decimal("20.72"),
        )
        self.assertEqual(
            digitalocean[("MI355X", "SPOT", 8)],
            Decimal("36.00"),
        )
        self.assertEqual(
            parse_tensorwave_price("<p>Starting at $2.95 /GPU HR</p>"),
            Decimal("2.95"),
        )
        self.assertEqual(
            parse_hotaisle_prices(
                """
                <p>Virtual machines $2.99/GPU/hr</p>
                <p>Bare metal Large 8x MI300x $3.39/GPU/hr</p>
                """
            ),
            (Decimal("2.99"), Decimal("3.39")),
        )
        self.assertEqual(
            parse_price_card(
                """
                <div class="cro-table_row">
                  <div class="cro-table_feature">AMD MI355X</div>
                  <div>As low as $4.29/GPUhr</div>
                </div>
                """
            ),
            Decimal("4.29"),
        )
        self.assertEqual(
            parse_ranges(
                """
                <section id="pricing">
                  <h3>On-Demand</h3><h4>$5.75</h4>
                  <h5>Reserved</h5><h4>$5.25</h4>
                </section>
                """
            ),
            {
                "On-Demand": ("5.75", "$5.75"),
                "Reserve": ("5.25", "$5.25"),
            },
        )


if __name__ == "__main__":
    unittest.main()
