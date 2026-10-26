from __future__ import annotations

import bisect
import json
import math
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


def _get_json(client: HttpClient, url: str) -> tuple[dict[str, object], str, bool]:
    try:
        payload = client.get_json(url, headers={"Accept": "application/json"})
        return payload, url, False
    except FetchError:
        text, proxy_url = client.read_proxy_text(url)
        payload = _proxied_json(text)
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected Kalshi payload from {url}")
        return payload, proxy_url, True


def _same_sign(left: float, right: float) -> bool:
    return left != 0 and right != 0 and (left > 0) == (right > 0)


def _endpoint_slope(h0: float, h1: float, d0: float, d1: float) -> float:
    slope = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if not _same_sign(slope, d0):
        return 0.0
    if not _same_sign(d0, d1) and abs(slope) > abs(3 * d0):
        return 3 * d0
    return slope


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
        slopes = [_endpoint_slope(hs[0], hs[1], deltas[0], deltas[1])]
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
        slopes.append(_endpoint_slope(hs[-1], hs[-2], deltas[-1], deltas[-2]))

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

    knots = list(points_by_day.values())
    for contract in ("weekly", "monthly"):
        knots.extend(
            (float(point["expiry_ts"]), float(point["price"]))
            for point in curve.get("forward", [])
            if point.get("contract") == contract
        )
    deduplicated = {timestamp: value for timestamp, value in sorted(knots)}
    ordered = sorted(deduplicated.items())
    xs = [item[0] for item in ordered]
    ys = [math.log(item[1]) for item in ordered]
    return math.exp(pchip(xs, ys, target.timestamp()))


def collect(
    rows: list[SourceRow], client: HttpClient, now: datetime
) -> list[Observation]:
    observations: list[Observation] = []
    for row in rows:
        model = row.gpu_model_code
        curve_url = f"{BASE_URL}/{model}"
        history_url = f"{curve_url}/history"
        curve, curve_source, curve_proxied = _get_json(client, curve_url)
        history, _, history_proxied = _get_json(client, history_url)
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
