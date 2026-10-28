from __future__ import annotations

import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, ok
from gpu_prices.providers.common import parse_price, run_provider_cli, text

URL = "https://www.daytona.io/pricing"
MIRROR_URL_TEMPLATE = "https://getdeploying.com/gpus/nvidia-{model}"
PANEL_LABELS = {
    "On-Demand": "On-demand GPU prices per hour",
    "Spot": "Preemptible GPU prices per hour",
}


def parse_panels(html: str) -> dict[str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, dict[str, str]] = {}
    for price_type, label in PANEL_LABELS.items():
        copies: list[dict[str, str]] = []
        for panel in soup.select(f'[role="tabpanel"][aria-label="{label}"]'):
            values: dict[str, str] = {}
            for container in panel.find_all("div"):
                name = container.select_one('[data-framer-name="GPU Name"]')
                price = container.select_one('[data-framer-name="GPU Price"]')
                if name is not None and price is not None:
                    values[text(name)] = text(price)
            for row in panel.select('[data-framer-name="Range"]'):
                match = re.fullmatch(
                    r"(Nvidia [A-Za-z0-9 ]+)\s+(\$[0-9.]+/h)",
                    text(row),
                )
                if match:
                    values[match.group(1)] = match.group(2)
            if values:
                copies.append(values)
        if not copies:
            raise ValueError(f"Daytona panel {label!r} was not found")
        if any(copy != copies[0] for copy in copies[1:]):
            raise ValueError(f"Daytona responsive copies disagree for {label!r}")
        result[price_type] = copies[0]
    return result


def parse_getdeploying_daytona(
    content: str,
    model: str,
) -> dict[str, str]:
    start = content.find("### [Daytona]")
    if start < 0:
        raise ValueError(f"GetDeploying omitted its Daytona {model} section")
    end = content.find("\n### [", start + 1)
    section = content[start : end if end >= 0 else None]
    result: dict[str, str] = {}
    for price_type, label in (("On-Demand", "On-Demand"), ("Spot", "Spot")):
        match = re.search(
            rf"{label}\s+from\s+\$([0-9.]+)",
            section,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(
                f"GetDeploying Daytona section omitted {model} {price_type}"
            )
        result[price_type] = match.group(1)
    return result


def _fetch_mirror(
    client: HttpClient,
    model: str,
) -> tuple[dict[str, str], str]:
    url = MIRROR_URL_TEMPLATE.format(model=model.lower())
    try:
        content = client.get_text(url)
        return parse_getdeploying_daytona(content, model), url
    except FetchError:
        pass
    last_error: ValueError | None = None
    for attempt in range(4):
        separator = "&" if "?" in url else "?"
        candidate = (
            url
            if attempt < 2
            else f"{url}{separator}collector_retry={int(time.time())}-{attempt}"
        )
        content, source_url = client.read_proxy_text(candidate)
        try:
            return parse_getdeploying_daytona(content, model), source_url
        except ValueError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt + 1)
    raise last_error or ValueError(f"Daytona mirror remained unavailable for {model}")


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    panels = parse_panels(client.get_text(URL))
    mirrors = {
        model: _fetch_mirror(client, model)
        for model in sorted({row.gpu_model_code for row in rows})
    }
    observations: list[Observation] = []
    for row in rows:
        direct_raw = panels[row.price_type].get(f"Nvidia {row.gpu_model_code}", "")
        mirror, mirror_source = mirrors[row.gpu_model_code]
        mirror_raw = mirror[row.price_type]
        direct_matches = bool(
            direct_raw and parse_price(direct_raw) == parse_price(mirror_raw)
        )
        raw = direct_raw if direct_matches else mirror_raw
        source_url = URL if direct_matches else mirror_source
        note = (
            "Published GPU-only rate in USD per GPU-hour; Spot maps to Daytona's "
            "Preemptible tier. Cross-checked against GetDeploying's provider-specific "
            "Daytona listing."
        )
        if not direct_matches:
            note += (
                f" Mirror value used because Daytona's server-rendered cell was "
                f"{direct_raw or 'missing'}."
            )
        observations.append(
            ok(
                row,
                parse_price(raw),
                fetched_at=now,
                source_url=source_url,
                raw_value=raw,
                note=note,
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Daytona")
