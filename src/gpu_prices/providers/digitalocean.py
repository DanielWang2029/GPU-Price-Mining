from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.digitalocean.com/pricing/gpu-droplets"
SECTIONS = {
    "Reserve": "reserved-plans",
    "Spot": "spot-plans",
    "On-Demand": "on-demand-plans",
}
MODELS = {
    "B300": "NVIDIA HGX B300",
    "H200": "NVIDIA HGX H200",
}


def parse_prices(html: str) -> dict[tuple[str, str], tuple[object, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[tuple[str, str], tuple[object, str]] = {}
    for price_type, section_id in SECTIONS.items():
        section = soup.select_one(f"#{section_id}")
        if section is None:
            raise ValueError(f"DigitalOcean omitted section {section_id}")
        for model, label in MODELS.items():
            heading = next(
                (node for node in section.find_all("h3") if text(node) == label),
                None,
            )
            if heading is None:
                continue
            card_text = ""
            for ancestor in heading.parents:
                candidate = text(ancestor)
                if "/GPU/hour" in candidate and "$" in candidate:
                    card_text = candidate
                    break
            if not card_text:
                raise ValueError(f"DigitalOcean {price_type} {model} card had no price")
            raw = card_text.split("$", 1)[1].split("/GPU/hour", 1)[0]
            result[(model, price_type)] = (parse_price(raw), f"${raw}")
    return result


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    prices = parse_prices(client.get_text(URL))
    observations: list[Observation] = []
    for row in rows:
        if row.price_type == "Reserve" and row.term != 12:
            raise ValueError(f"DigitalOcean reserve term must be 12, got {row.term}")
        value, raw = prices[(row.gpu_model_code, row.price_type)]
        observations.append(
            ok(
                row,
                value,
                fetched_at=now,
                source_url=URL,
                raw_value=raw,
                note="Published USD per GPU-hour pricing card.",
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Digital Ocean")
