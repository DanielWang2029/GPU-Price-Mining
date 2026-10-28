from __future__ import annotations

import json
import unittest

from gpu_prices.providers.aws import (
    parse_capacity_prices,
    parse_spot_prices,
)
from gpu_prices.providers.bentaus import parse_ranges
from gpu_prices.providers.civo import parse_prices as parse_civo_prices
from gpu_prices.providers.cyfuture_ai import parse_b300_row
from gpu_prices.providers.digitalocean import (
    parse_prices as parse_digitalocean_prices,
)
from gpu_prices.providers.impossible_cloud import parse_offers
from gpu_prices.providers.latitude_sh import parse_plan


class NewProviderParserTests(unittest.TestCase):
    def test_impossible_cloud_selects_first_numeric_capacity(self) -> None:
        html = """
        <div class="baremetal-gpu-item">
          <span fs-cmsfilter-field="GPU">B200</span>
          <div class="gpu-info-wrapper first-row">
            <span class="gpu-nodes-wrapper">By Request</span>
          </div>
          <span fs-cmsfilter-field="location">US</span>
          <span fs-cmsfilter-field="Duration">12 months</span>
          <span fs-list-field="price">7.35</span>
        </div>
        <div class="baremetal-gpu-item">
          <span fs-cmsfilter-field="GPU">B200</span>
          <div class="gpu-info-wrapper first-row">
            <span class="gpu-nodes-wrapper">160 • 20 nodes</span>
          </div>
          <span fs-cmsfilter-field="location">EU</span>
          <span fs-cmsfilter-field="Duration">60 months</span>
          <span fs-list-field="price">4.0</span>
        </div>
        """
        offers = parse_offers(html)
        self.assertEqual(str(offers["B200"]["price"]), "4.00")
        self.assertEqual(offers["B200"]["region"], "Europe")
        self.assertEqual(offers["B200"]["term"], 60)

    def test_digitalocean_reads_scoped_price_cards(self) -> None:
        html = """
        <section id="reserved-plans">
          <div><h3>NVIDIA HGX B300</h3><p>$7.94 /GPU/hour</p></div>
          <div><h3>NVIDIA HGX H200</h3><p>$3.40 /GPU/hour</p></div>
        </section>
        <section id="spot-plans">
          <div><h3>NVIDIA HGX B300</h3><p>$6.17 /GPU/hour</p></div>
        </section>
        <section id="on-demand-plans">
          <div><h3>NVIDIA HGX H200</h3><p>$4.47 /GPU/hour</p></div>
        </section>
        """
        prices = parse_digitalocean_prices(html)
        self.assertEqual(str(prices[("B300", "Reserve")][0]), "7.94")
        self.assertEqual(str(prices[("H200", "On-Demand")][0]), "4.47")

    def test_bentaus_selects_lower_range_bound(self) -> None:
        html = """
        <section id="pricing">
          <h3>On-Demand</h3><h4>$6.50 – $8.50</h4>
          <h5>Reserved</h5><h4>$4.35 - $6.50</h4>
        </section>
        """
        ranges = parse_ranges(html)
        self.assertEqual(ranges["On-Demand"][0], "6.50")
        self.assertEqual(ranges["Reserve"][0], "4.35")

    def test_civo_normalizes_multi_gpu_node_prices(self) -> None:
        html = """
        <table>
          <caption>NVIDIA B300 GPU pricing</caption>
          <tbody><tr>
            <td>Extra Large 8 x NVIDIA B300</td>
            <td class="on-demand-pricing">
              <span class="price-value" data-option="hourly">$59.92 per hour</span>
            </td>
            <td><span id="36_months">
              <span class="price-value" data-option="hourly">$43.92 per hour</span>
            </span></td>
          </tr></tbody>
        </table>
        """
        prices = parse_civo_prices(html)
        self.assertEqual(str(prices[("B300", "On-Demand")][0]), "7.49")
        self.assertEqual(str(prices[("B300", "Reserve")][0]), "5.49")

    def test_cyfuture_reads_single_gpu_b300_row(self) -> None:
        markdown = """
        | 1B300.32v.256m | NVIDIA 1xB300 (1X) | 288 | 75 | 2250 | 32 |
        256 | 1800 | 800 | 8000 | - | ₹ 570 | ₹ 546 | ₹ 523 | Reserve |
        """
        cells = parse_b300_row(markdown.replace("\n256", " 256"))
        self.assertEqual(cells[0], "1B300.32v.256m")
        self.assertEqual(cells[11], "₹ 570")

    def test_latitude_reads_embedded_plan_data(self) -> None:
        payload = {
            "servers": [
                {
                    "attributes": {
                        "slug": "g4-b300-large",
                        "specs": {"gpu": {"count": 8}},
                        "regions": [
                            {
                                "name": "United States",
                                "pricing": {
                                    "USD": {
                                        "hour": 128,
                                        "month": 46720,
                                        "year": 392448,
                                    }
                                },
                            }
                        ],
                    }
                }
            ]
        }
        plan = parse_plan(f'<script>"plansData":{json.dumps(payload)}</script>')
        self.assertEqual(plan["slug"], "g4-b300-large")
        self.assertEqual(plan["specs"]["gpu"]["count"], 8)

    def test_aws_parses_capacity_and_spot_rates(self) -> None:
        html = """
        <h2>P6-B300 Pricing</h2><table><tr>
          <td>p6-b300.48xlarge</td><td>US West (Oregon)</td>
          <td>$129.168 USD ($16.146 USD)</td>
        </tr></table>
        <h2>P6-B200 Pricing</h2><table><tr>
          <td>p6-b200.48xlarge</td><td>US East (Ohio)</td>
          <td>$113.666 USD ($14.208 USD)</td>
        </tr></table>
        <h2>P6e Pricing</h2><table><tr>
          <td>u-p6e-gb200x72</td><td>US East (Dallas) Local Zone</td>
          <td>$761.904 ($10.582 USD)</td>
        </tr></table>
        """
        capacity = parse_capacity_prices(html)
        self.assertEqual(str(capacity["B300"][0]), "16.146")
        payload = {
            "config": {
                "regions": [
                    {
                        "region": "us-east-1",
                        "instanceTypes": [
                            {
                                "sizes": [
                                    {
                                        "size": "p6-b300.48xlarge",
                                        "valueColumns": [
                                            {
                                                "name": "linux",
                                                "prices": {"USD": "77.3746"},
                                            }
                                        ],
                                    },
                                    {
                                        "size": "p6-b200.48xlarge",
                                        "valueColumns": [
                                            {
                                                "name": "linux",
                                                "prices": {"USD": "83.7053"},
                                            }
                                        ],
                                    },
                                ]
                            }
                        ],
                    }
                ]
            }
        }
        spot = parse_spot_prices(payload)
        self.assertEqual(str(spot["B300"][0]), "9.671825")
        self.assertEqual(str(spot["B200"][0]), "10.4631625")


if __name__ == "__main__":
    unittest.main()
