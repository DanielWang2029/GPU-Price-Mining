from __future__ import annotations

import unittest

from gpu_prices.window_load import normalize_aws_terms, render_provider_sql


class WindowLoadTests(unittest.TestCase):
    def test_aws_capacity_terms_are_six_months(self) -> None:
        rows = [
            {
                "provider_id": "aws",
                "billing_type": "RESERVATION",
                "source_url": "https://aws.amazon.com/ec2/capacityblocks/pricing/",
                "term_months": "-1",
            },
            {
                "provider_id": "aws",
                "billing_type": "SPOT",
                "source_url": "https://website.spot.ec2.aws.a2z.com/spot.json",
                "term_months": "0",
            },
        ]
        normalize_aws_terms(rows)
        self.assertEqual(rows[0]["term_months"], "6")
        self.assertEqual(rows[1]["term_months"], "0")

    def test_provider_sql_uses_source_specific_replacement_windows(self) -> None:
        columns = {
            "price_date": "2026-11-09",
            "run_date": "2026-11-19",
            "gpu_id": "nvidia-h100",
            "gpu_model_code": "H100",
            "billing_type": "ON_DEMAND",
            "term_months": "0",
            "provider_id": "silicondata",
            "median_price": "3.01",
            "offering_count": "1",
            "supplier_type": "GPU Cloud",
            "reference_url": "https://portal.silicondata.com/silicon-index",
            "source_label": "GPU INDEX",
        }
        sql = render_provider_sql(
            rows=[columns],
            start_date="2026-11-01",
            index_start_date="2026-11-09",
            end_date="2026-11-19",
        )
        self.assertIn(
            "source_label = 'price_mining' AND price_date BETWEEN "
            "'2026-11-01' AND '2026-11-19'",
            sql,
        )
        self.assertIn(
            "source_label = 'GPU INDEX' AND provider_id IN ('silicondata') "
            "AND price_date BETWEEN '2026-11-09' AND '2026-11-19'",
            sql,
        )
        self.assertNotIn("public.public.", sql)


if __name__ == "__main__":
    unittest.main()
