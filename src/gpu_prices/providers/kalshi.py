from __future__ import annotations

import bisect
import json
import math
import time
from datetime import datetime, timezone

from gpu_prices.http import FetchError, HttpClient
from gpu_prices.models import Observation, SourceRow, money_2, ok
from gpu_prices.providers.common import run_provider_cli

BASE_URL = "https://kalshi.com/api-app/compute/forward-curve"


def _proxied_json(text: str) -> object:
    marker = "Markdown Content:"
    if marker not in text:
        raise ValueError("Read proxy response did not contain a JSON payload")
    return json.loads(text.split(marker, 1)[1].strip())


def _get_json(
    client: HttpClient,
    url: str,
    *,
    skip_direct: bool = False,
) -> tuple[dict[str, object], str, bool]:
    if not skip_direct:
        try:
            payload = client.get_json(url, headers={"Accept": "application/json"})
            return payload, url, False
        except FetchError:
            pass

    last_error: Exception | None = None
    for attempt in range(6):
        separator = "&" if "?" in url else "?"
        candidate = (
            url
            if attempt < 3
            else f"{url}{separator}collector_retry={int(time.time())}-{attempt}"
        )
        try:
            text, proxy_url = client.read_proxy_text(candidate)
            payload = _proxied_json(text)
            if not isinstance(payload, dict):
                raise ValueError(f"Unexpected Kalshi payload from {url}")
            return payload, proxy_url, True
        except (FetchError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(min(attempt + 1, 3))
    raise ValueError(f"Kalshi JSON remained unavailable at {url}: {last_error}")


def _same_sign(left: float, right: float) -> bool:
    return left != 0 and right != 0 and (left > 0) == (right > 0)


def pchip(xs: list[float], ys: list[float], target: float) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("PCHIP requires at least two paired points")
    if any(right <= left for left, right in zip(xs, xs[1:])):
        raise ValueError("PCHIP x values must be strictly increasing")

    hs = [right - left for left, right in zip(xs, xs[1:])]
    deltas = [(right - left) / width for left, right, width in zip(ys, ys[1:], hs)]
    if len(xs) == 2:
        slopes = [deltas[0], deltas[0]]
    else:
        slopes = [deltas[0]]
        for index in range(1, len(xs) - 1):
            before = deltas[index - 1]
            after = deltas[index]
            if not _same_sign(before, after):
                slopes.append(0.0)
                continue
            weight_1 = 2 * hs[index] + hs[index - 1]
            weight_2 = hs[index] + 2 * hs[index - 1]
            slopes.append(
                (weight_1 + weight_2) / (weight_1 / before + weight_2 / after)
            )
        slopes.append(deltas[-1])

    index = max(0, min(bisect.bisect_right(xs, target) - 1, len(xs) - 2))
    width = hs[index]
    scaled = (target - xs[index]) / width
    h00 = (2 * scaled**3) - (3 * scaled**2) + 1
    h10 = scaled**3 - (2 * scaled**2) + scaled
    h01 = (-2 * scaled**3) + (3 * scaled**2)
    h11 = scaled**3 - scaled**2
    return (
        h00 * ys[index]
        + h10 * width * slopes[index]
        + h01 * ys[index + 1]
        + h11 * width * slopes[index + 1]
    )


def curve_value(
    curve: dict[str, object],
    history: dict[str, object],
    target: datetime,
) -> float:
    points_by_day: dict[object, tuple[float, float]] = {}
    for point in history.get("points", []):
        timestamp = float(point["ts"])
        day = datetime.fromtimestamp(timestamp, timezone.utc).date()
        points_by_day[day] = (timestamp, float(point["value"]))

    spot = curve["spot"]
    spot_timestamp = float(spot["ts"])
    spot_day = datetime.fromtimestamp(spot_timestamp, timezone.utc).date()
    points_by_day[spot_day] = (spot_timestamp, float(spot["value"]))

    forward = list(curve.get("forward", []))
    first_forward = min(
        (float(point["expiry_ts"]) for point in forward),
        default=float("inf"),
    )
    knots = [point for point in points_by_day.values() if point[0] < first_forward]
    for contract in ("weekly", "monthly"):
        knots.extend(
            (float(point["expiry_ts"]), float(point["price"]))
            for point in forward
            if point.get("contract") == contract
        )
    deduplicated = {timestamp: value for timestamp, value in sorted(knots)}
    ordered = sorted(deduplicated.items())
    xs = [item[0] for item in ordered]
    ys = [math.log(item[1]) for item in ordered]
    target_timestamp = max(xs[0], min(target.timestamp(), xs[-1]))
    return math.exp(pchip(xs, ys, target_timestamp))


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    observations: list[Observation] = []
    prefer_proxy = False
    for row in rows:
        model = row.gpu_model_code
        curve_url = f"{BASE_URL}/{model}"
        history_url = f"{curve_url}/history"
        curve, curve_source, curve_proxied = _get_json(
            client, curve_url, skip_direct=prefer_proxy
        )
        prefer_proxy = prefer_proxy or curve_proxied
        history, _, history_proxied = _get_json(
            client, history_url, skip_direct=prefer_proxy
        )
        prefer_proxy = prefer_proxy or history_proxied
        value = curve_value(curve, history, now)
        note = "Forward-curve tooltip value interpolated with log-PCHIP at collection time."
        if curve_proxied or history_proxied:
            note += " Direct access was blocked; public read proxy used."
        observations.append(
            ok(
                row,
                money_2(value),
                fetched_at=now,
                source_url=curve_source,
                effective_at=now.isoformat(),
                raw_value=f"{value:.8f}",
                note=note,
            )
        )
    return observations


if __name__ == "__main__":
    run_provider_cli("Kalshi")
