from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from gpu_prices.providers.astra_intellectus import parse_visible_offers
from gpu_prices.providers.daytona import (
    parse_getdeploying_daytona,
    parse_panels,
)
from gpu_prices.providers.getdeploying import (
    chart_money_2,
    parse_dataset_prices,
    parse_history_prices,
    select_reservation_chart_row,
)
from gpu_prices.providers.hyperbolic import parse_marketplace
from gpu_prices.providers.kalshi import pchip
from gpu_prices.providers.silicondata import (
    parse_index_history,
    parse_index_page,
)
from gpu_prices.providers.upcloud import (
    parse_getdeploying_mirror,
    parse_public_page,
)
from gpu_prices.workbook import load_source_rows

ROOT = Path(__file__).resolve().parents[1]


class WorkbookTests(unittest.TestCase):
    def test_source_workbook_has_one_normalized_row_per_request(self) -> None:
        rows = load_source_rows(ROOT / "算力价格爬虫数据整理.xlsx")
        self.assertEqual(len(rows), 122)
        self.assertEqual(len({row.workbook_row for row in rows}), 122)
        self.assertEqual(len({row.source_name for row in rows}), 25)
        identities = {
            (
                row.source_name,
                row.gpu_model_code,
                row.price_type,
                row.term,
            )
            for row in rows
        }
        self.assertIn(("Gpu.ai", "B300", "On-Demand", None), identities)
        self.assertIn(("Together.ai", "H200", "Reserve", Decimal("1")), identities)
        self.assertIn(("Together.ai", "H200", "Reserve", Decimal("3")), identities)
        self.assertIn(("Together.ai", "H200", "Reserve", Decimal("6")), identities)
        self.assertIn(("TheAI Cloud", "B300", "Reserve", Decimal("24")), identities)
        self.assertTrue(
            all(
                value == value.strip()
                for row in rows
                for value in (
                    row.source_name,
                    row.gpu_model_code,
                    row.price_type,
                    row.region,
                    row.cloud_type,
                    row.url,
                )
            )
        )


class ParserTests(unittest.TestCase):
    def test_pchip_interpolates_a_line(self) -> None:
        self.assertAlmostEqual(pchip([0.0, 1.0], [0.0, 1.0], 0.25), 0.25)

    def test_silicondata_reads_structured_index_payload(self) -> None:
        html = (
            '<script>{"rawValue":"7.02","change":"1.0% (7D)",'
            '"asOf":"As of Oct 20, 2026","points":[]}</script>'
        )
        value, raw, effective_at = parse_index_page(html)
        self.assertEqual(str(value), "7.02")
        self.assertEqual(raw, "7.02")
        self.assertEqual(effective_at, "As of Oct 20, 2026")

    def test_silicondata_reads_explicit_daily_points(self) -> None:
        html = (
            '<script>{"rawValue":"7.02","points":['
            '{"date":"2026-10-01","price":6.78},'
            '{"date":"2026-10-02","price":6.80}]}</script>'
        )
        values = parse_index_history(html)
        self.assertEqual(str(values["2026-10-01"]), "6.78")
        self.assertEqual(str(values["2026-10-02"]), "6.8")

    def test_getdeploying_reads_only_price_history_summary(self) -> None:
        text = """
        ## Price history
        Weekly median price per GPU per hour
        On-demand$8.99
        Reserved$5.72
        Spot$5.49
        ## At a glance
        Median price (current)$99.99
        """
        values = parse_history_prices(text)
        self.assertEqual(str(values["On-Demand"][0]), "8.99")
        self.assertEqual(str(values["Reserve"][0]), "5.72")
        self.assertEqual(str(values["Spot"][0]), "5.49")

    def test_getdeploying_matches_javascript_display_rounding(self) -> None:
        self.assertEqual(chart_money_2("8.625"), Decimal("8.63"))
        self.assertEqual(chart_money_2("5.265"), Decimal("5.26"))

    def test_getdeploying_dataset_fills_client_rendered_chart(self) -> None:
        csv_text = """gpu_slug,date,billing_type,reservation_months,min_price,max_price,median_price,provider_median_price,provider_count,offering_count
nvidia-b200,2026-10-26,ON_DEMAND,,3.75,12,6.62,7.99,20,40
nvidia-b200,2026-10-26,SPOT,,3.59,8,4.77,4.38,8,12
nvidia-b200,2026-10-26,RESERVATION,6,3.99,8,6.12,6.13,2,2
nvidia-b200,2026-10-26,RESERVATION,12,3.99,8,6.67,6.67,4,4
"""
        values = parse_dataset_prices(csv_text)
        self.assertEqual(str(values["On-Demand"][0]), "7.99")
        self.assertEqual(str(values["Spot"][0]), "4.38")
        self.assertEqual(str(values["Reserve"][0]), "6.67")
        self.assertIn("12 months", values["Reserve"][2])

    def test_getdeploying_reserve_uses_weighted_chart_median(self) -> None:
        rows = [
            {
                "billing_type": "RESERVATION",
                "reservation_months": months,
                "provider_median_price": price,
                "offering_count": count,
            }
            for months, price, count in (
                ("", "4.25", "1"),
                ("60", "4.53", "1"),
                ("36", "5.00", "5"),
                ("6", "5.7531", "4"),
                ("24", "5.99", "5"),
                ("1", "6.0031", "4"),
                ("12", "6.49", "6"),
            )
        ]
        selected = select_reservation_chart_row(rows)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["reservation_months"], "24")
        self.assertEqual(selected["provider_median_price"], "5.99")

    def test_upcloud_reads_one_gpu_usd_rows(self) -> None:
        markdown = """
        | GPU | CPU cores | RAM | Spot Price | Price |
        | --- | --- | --- | --- | --- |
        | 1 x NVIDIA B200 | 24 cores | 240 GB | **$4.23/h** | **$6.05/h** |
        | 1 x NVIDIA B300 | 28 cores | 240 GB | **$5.99/h** | **$7.99/h** |
        """
        values = parse_public_page(markdown)
        self.assertEqual(str(values[("B200", "Spot")][0]), "4.23")
        self.assertEqual(str(values[("B300", "On-Demand")][0]), "7.99")

    def test_upcloud_reads_scoped_mirror_summary(self) -> None:
        markdown = """
        ### [UpCloud](https://getdeploying.com/upcloud)
        On-Demand from $6.05
        Spot from $4.23
        ### [Another provider](https://example.com)
        On-Demand from $1.00
        """
        values = parse_getdeploying_mirror(markdown, "B200")
        self.assertEqual(str(values[("B200", "On-Demand")][0]), "6.05")
        self.assertEqual(str(values[("B200", "Spot")][0]), "4.23")

    def test_hyperbolic_reads_semantic_price_table(self) -> None:
        html = """
        <table>
          <thead><tr><th>GPU Type</th><th>Starting From (per GPU hour)</th></tr></thead>
          <tbody>
            <tr><td>Nvidia H200</td><td>$3.99 / HR</td></tr>
            <tr><td>Nvidia B200</td><td>$5.99 / HR</td></tr>
          </tbody>
        </table>
        """
        values = parse_marketplace(html)
        self.assertEqual(str(values["H200"][0]), "3.99")
        self.assertEqual(str(values["B200"][0]), "5.99")

    def test_astra_rejects_all_viewport_hidden_table(self) -> None:
        html = """
        <table class="bordered-table">
          <tr><th>GPU Type</th><th>vRAM</th><th>Region</th><th>Cluster</th>
              <th>Lease</th><th>Indicative Price</th></tr>
          <tr><td>NVIDIA B300 SXM 8-GPU</td><td>2.3TB</td><td>US #1</td>
              <td>128 nodes</td><td>3 years</td><td>$5.60/GPU/Hour</td></tr>
        </table>
        <div class="elementor-hidden-desktop elementor-hidden-tablet elementor-hidden-mobile">
          <table class="bordered-table">
            <tr><td>NVIDIA H200 SXM 8-GPU</td><td>1.1TB</td><td>US #2</td>
                <td>128 nodes</td><td>3 years</td><td>$3.42/GPU/Hour</td></tr>
          </table>
        </div>
        """
        offers = parse_visible_offers(html)
        self.assertEqual(str(offers["B300"][0][0]), "5.60")
        self.assertEqual(offers["H200"], [])

    def test_daytona_reads_named_and_range_gpu_rows(self) -> None:
        html = """
        <div role="tabpanel" aria-label="On-demand GPU prices per hour">
          <div><span data-framer-name="GPU Name">Nvidia B300</span>
               <span data-framer-name="GPU Price">$6.25/h</span></div>
          <div data-framer-name="Range">
            <span data-framer-name="type">Nvidia H200</span>
            <span data-framer-name="type">$4.54/h</span>
          </div>
        </div>
        <div role="tabpanel" aria-label="Preemptible GPU prices per hour">
          <div><span data-framer-name="GPU Name">Nvidia B300</span>
               <span data-framer-name="GPU Price">$4.08/h</span></div>
          <div data-framer-name="Range">
            <span data-framer-name="type">Nvidia H200</span>
            <span data-framer-name="type">$2.61/h</span>
          </div>
        </div>
        """
        panels = parse_panels(html)
        self.assertEqual(panels["On-Demand"]["Nvidia B300"], "$6.25/h")
        self.assertEqual(panels["Spot"]["Nvidia B300"], "$4.08/h")
        self.assertEqual(panels["On-Demand"]["Nvidia H200"], "$4.54/h")
        self.assertEqual(panels["Spot"]["Nvidia H200"], "$2.61/h")

    def test_daytona_mirror_is_scoped_to_daytona_provider(self) -> None:
        markdown = """
        ### [Daytona](https://getdeploying.com/daytona)
        On-Demand from $7.10
        Spot from $4.08
        ### [Another provider](https://example.com)
        On-Demand from $1.00
        """
        values = parse_getdeploying_daytona(markdown, "B300")
        self.assertEqual(values["On-Demand"], "7.10")
        self.assertEqual(values["Spot"], "4.08")


if __name__ == "__main__":
    unittest.main()
