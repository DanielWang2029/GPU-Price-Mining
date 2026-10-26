from __future__ import annotations

import unittest
from pathlib import Path

from gpu_prices.providers.astra_intellectus import parse_visible_offers
from gpu_prices.providers.daytona import parse_panels
from gpu_prices.providers.getdeploying import parse_history_prices
from gpu_prices.providers.kalshi import pchip
from gpu_prices.providers.silicondata import parse_index_page
from gpu_prices.providers.upcloud import parse_public_page
from gpu_prices.workbook import load_source_rows

ROOT = Path(__file__).resolve().parents[1]


class WorkbookTests(unittest.TestCase):
    def test_source_workbook_has_one_normalized_row_per_request(self) -> None:
        rows = load_source_rows(ROOT / "算力价格爬虫数据整理.xlsx")
        self.assertEqual(len(rows), 93)
        self.assertEqual(len({row.workbook_row for row in rows}), 93)
        self.assertEqual(len({row.source_name for row in rows}), 17)
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

    def test_daytona_requires_responsive_panels_to_agree(self) -> None:
        html = """
        <div role="tabpanel" aria-label="On-demand GPU prices per hour">
          <div><span data-framer-name="GPU Name">Nvidia B300</span>
               <span data-framer-name="GPU Price">$6.25/h</span></div>
        </div>
        <div role="tabpanel" aria-label="Preemptible GPU prices per hour">
          <div><span data-framer-name="GPU Name">Nvidia B300</span>
               <span data-framer-name="GPU Price">$4.08/h</span></div>
        </div>
        """
        panels = parse_panels(html)
        self.assertEqual(panels["On-Demand"]["Nvidia B300"], "$6.25/h")
        self.assertEqual(panels["Spot"]["Nvidia B300"], "$4.08/h")


if __name__ == "__main__":
    unittest.main()
