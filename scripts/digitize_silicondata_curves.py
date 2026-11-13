from __future__ import annotations

import argparse
import binascii
import csv
import math
import statistics
import struct
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

CURVE_RGB = (46, 99, 230)
COMPARISON_RGB = (225, 29, 72)
EXPECTED_IMAGE_SIZE = (3200, 1800)
PLOT_X_START = 272
PLOT_X_END = 2769
PLOT_Y_START = 640
PLOT_Y_END = 1360
PROVIDER_SERIES_TABLE = "public.compute_insight_gpu_provider_series_daily"
PROVIDER_SERIES_COLUMNS = (
    "price_date",
    "run_date",
    "gpu_id",
    "gpu_model_code",
    "billing_type",
    "term_months",
    "provider_id",
    "median_price",
    "offering_count",
    "supplier_type",
    "reference_url",
    "source_label",
)
GPU_IDS = {
    "B200": "nvidia-b200",
    "B300": "nvidia-b300",
    "H200": "nvidia-h200",
}
SOURCE_LABEL = "GPU INDEX"
REFERENCE_URL = "https://portal.silicondata.com/silicon-index"


@dataclass(frozen=True, slots=True)
class CurveConfig:
    model: str
    image_name: str
    start_date: date
    end_date: date
    start_price: float
    end_price: float
    low_date: date
    low_price: float
    high_date: date
    high_price: float


@dataclass(slots=True)
class Raster:
    width: int
    height: int
    pixels: bytearray

    def rgb(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * 3
        return tuple(self.pixels[offset : offset + 3])  # type: ignore[return-value]

    def set_rgb(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        offset = (y * self.width + x) * 3
        self.pixels[offset : offset + 3] = bytes(color)


CONFIGS = (
    CurveConfig(
        model="B300",
        image_name="gpu-index-b300-chart.png",
        start_date=date(2026, 4, 23),
        end_date=date(2026, 11, 10),
        start_price=4.83,
        end_price=7.68,
        low_date=date(2026, 4, 23),
        low_price=4.83,
        high_date=date(2026, 11, 7),
        high_price=7.69,
    ),
    CurveConfig(
        model="B200",
        image_name="gpu-index-b200-chart.png",
        start_date=date(2025, 8, 1),
        end_date=date(2026, 11, 10),
        start_price=5.31,
        end_price=6.97,
        low_date=date(2026, 1, 11),
        low_price=4.29,
        high_date=date(2026, 11, 10),
        high_price=6.97,
    ),
    CurveConfig(
        model="H200",
        image_name="gpu-index-h200-chart.png",
        start_date=date(2026, 5, 4),
        end_date=date(2026, 11, 10),
        start_price=2.70,
        end_price=3.48,
        low_date=date(2026, 5, 9),
        low_price=2.68,
        high_date=date(2026, 11, 8),
        high_price=3.55,
    ),
)


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def read_png(path: Path) -> Raster:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")

    width = height = bit_depth = color_type = interlace = 0
    compressed = bytearray()
    position = 8
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_name = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += length + 12
        if chunk_name == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
        elif chunk_name == b"IDAT":
            compressed.extend(payload)
        elif chunk_name == b"IEND":
            break

    if bit_depth != 8 or color_type not in {2, 6} or interlace:
        raise ValueError(
            f"Unsupported PNG layout in {path}: "
            f"bit_depth={bit_depth}, color_type={color_type}, interlace={interlace}"
        )
    channels = 3 if color_type == 2 else 4
    decompressed = zlib.decompress(compressed)
    stride = width * channels
    expected_size = height * (stride + 1)
    if len(decompressed) != expected_size:
        raise ValueError(
            f"Unexpected decompressed size in {path}: "
            f"{len(decompressed)} != {expected_size}"
        )

    pixels = bytearray(width * height * 3)
    previous = bytearray(stride)
    source_offset = 0
    destination_offset = 0
    for _ in range(height):
        filter_type = decompressed[source_offset]
        scanline = bytearray(
            decompressed[source_offset + 1 : source_offset + stride + 1]
        )
        source_offset += stride + 1
        for index in range(stride):
            left = scanline[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 255
            elif filter_type == 2:
                scanline[index] = (scanline[index] + up) & 255
            elif filter_type == 3:
                scanline[index] = (scanline[index] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                scanline[index] = (
                    scanline[index] + _paeth(left, up, upper_left)
                ) & 255
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter {filter_type} in {path}")
        for index in range(0, stride, channels):
            pixels[destination_offset : destination_offset + 3] = scanline[
                index : index + 3
            ]
            destination_offset += 3
        previous = scanline
    return Raster(width=width, height=height, pixels=pixels)


def _png_chunk(name: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(name)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + name
        + payload
        + struct.pack(">I", checksum)
    )


def write_png(path: Path, raster: Raster) -> None:
    scanlines = bytearray()
    stride = raster.width * 3
    for row in range(raster.height):
        scanlines.append(0)
        start = row * stride
        scanlines.extend(raster.pixels[start : start + stride])
    content = bytearray(b"\x89PNG\r\n\x1a\n")
    content.extend(
        _png_chunk(
            b"IHDR",
            struct.pack(
                ">IIBBBBB",
                raster.width,
                raster.height,
                8,
                2,
                0,
                0,
                0,
            ),
        )
    )
    content.extend(_png_chunk(b"IDAT", zlib.compress(scanlines, level=9)))
    content.extend(_png_chunk(b"IEND", b""))
    path.write_bytes(content)


def _curve_candidates(raster: Raster) -> dict[int, list[int]]:
    candidates: dict[int, list[int]] = {}
    for x in range(PLOT_X_START, PLOT_X_END + 1):
        ys = [
            y
            for y in range(PLOT_Y_START, PLOT_Y_END + 1)
            if raster.rgb(x, y) == CURVE_RGB
        ]
        if ys:
            candidates[x] = ys
    return candidates


def extract_centerline(
    raster: Raster,
) -> tuple[dict[int, float], dict[int, list[int]]]:
    if (raster.width, raster.height) != EXPECTED_IMAGE_SIZE:
        raise ValueError(
            f"Expected {EXPECTED_IMAGE_SIZE[0]}x{EXPECTED_IMAGE_SIZE[1]} image, "
            f"got {raster.width}x{raster.height}"
        )
    candidates = _curve_candidates(raster)
    if len(candidates) < (PLOT_X_END - PLOT_X_START) * 0.9:
        raise ValueError(
            f"Only found curve pixels in {len(candidates)} chart columns"
        )

    observed = {
        x: float(statistics.median(ys)) for x, ys in candidates.items()
    }
    known_xs = sorted(observed)
    centerline: dict[int, float] = {}
    right_index = 0
    for x in range(PLOT_X_START, PLOT_X_END + 1):
        if x in observed:
            centerline[x] = observed[x]
            continue
        while right_index < len(known_xs) and known_xs[right_index] < x:
            right_index += 1
        if right_index == 0:
            centerline[x] = observed[known_xs[0]]
        elif right_index == len(known_xs):
            centerline[x] = observed[known_xs[-1]]
        else:
            left_x = known_xs[right_index - 1]
            right_x = known_xs[right_index]
            fraction = (x - left_x) / (right_x - left_x)
            centerline[x] = observed[left_x] + fraction * (
                observed[right_x] - observed[left_x]
            )

    # The current-price marker is an open blue circle that overlaps the final
    # few line segments. Follow the incoming trace through that marker instead
    # of taking the median of its upper and lower arcs.
    previous_y = centerline[PLOT_X_END - 25]
    for x in range(PLOT_X_END - 24, PLOT_X_END):
        ys = candidates.get(x)
        if ys and max(ys) - min(ys) > 12:
            centerline[x] = float(min(ys, key=lambda y: abs(y - previous_y)))
        previous_y = centerline[x]
    # The marker's vertical center is still the correct end-price calibration.
    centerline[PLOT_X_END] = float(
        statistics.median(candidates[PLOT_X_END])
    )
    return centerline, candidates


def _calendar_dates(start: date, end: date) -> list[date]:
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]


def _date_x(config: CurveConfig, value: date) -> float:
    total_days = (config.end_date - config.start_date).days
    elapsed_days = (value - config.start_date).days
    return PLOT_X_START + (PLOT_X_END - PLOT_X_START) * (
        elapsed_days / total_days
    )


def _interpolate_centerline(centerline: dict[int, float], x: float) -> float:
    left = max(PLOT_X_START, min(PLOT_X_END, math.floor(x)))
    right = max(PLOT_X_START, min(PLOT_X_END, math.ceil(x)))
    if left == right:
        return centerline[left]
    fraction = x - left
    return centerline[left] + fraction * (centerline[right] - centerline[left])


def estimate_curve(
    config: CurveConfig,
    centerline: dict[int, float],
) -> tuple[list[tuple[date, float]], float, float]:
    start_y = centerline[PLOT_X_START]
    end_y = centerline[PLOT_X_END]
    if abs(start_y - end_y) < 1:
        raise ValueError(f"Invalid endpoint calibration for {config.model}")

    def y_to_price(y: float) -> float:
        fraction = (start_y - y) / (start_y - end_y)
        return config.start_price + fraction * (
            config.end_price - config.start_price
        )

    estimates: list[tuple[date, float]] = []
    anchors = {
        config.start_date: config.start_price,
        config.end_date: config.end_price,
        config.low_date: config.low_price,
        config.high_date: config.high_price,
    }
    for current_date in _calendar_dates(config.start_date, config.end_date):
        y = _interpolate_centerline(centerline, _date_x(config, current_date))
        price = min(config.high_price, max(config.low_price, y_to_price(y)))
        price = anchors.get(current_date, price)
        estimates.append((current_date, round(price + 1e-10, 2)))
    return estimates, start_y, end_y


def _draw_line(
    raster: Raster,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = 3,
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        radius = thickness // 2
        for y_offset in range(-radius, radius + 1):
            for x_offset in range(-radius, radius + 1):
                raster.set_rgb(x0 + x_offset, y0 + y_offset, color)
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def write_comparison_png(
    path: Path,
    raster: Raster,
    config: CurveConfig,
    estimates: list[tuple[date, float]],
    start_y: float,
    end_y: float,
) -> None:
    def price_y(price: float) -> int:
        fraction = (price - config.start_price) / (
            config.end_price - config.start_price
        )
        return round(start_y - fraction * (start_y - end_y))

    points = [
        (round(_date_x(config, current_date)), price_y(price))
        for current_date, price in estimates
    ]
    for start, end in zip(points, points[1:]):
        _draw_line(raster, start, end, COMPARISON_RGB)
    write_png(path, raster)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def reconstruction_metrics(
    config: CurveConfig,
    estimates: list[tuple[date, float]],
    start_y: float,
    end_y: float,
    centerline: dict[int, float],
    candidates: dict[int, list[int]],
) -> dict[str, float]:
    by_date = dict(estimates)
    daily_dates = [current_date for current_date, _ in estimates]

    def reconstructed_price(x: int) -> float:
        date_position = (x - PLOT_X_START) / (PLOT_X_END - PLOT_X_START)
        day_position = date_position * (len(daily_dates) - 1)
        left_index = max(0, min(len(daily_dates) - 1, math.floor(day_position)))
        right_index = max(0, min(len(daily_dates) - 1, math.ceil(day_position)))
        left_price = by_date[daily_dates[left_index]]
        right_price = by_date[daily_dates[right_index]]
        if left_index == right_index:
            return left_price
        fraction = day_position - left_index
        return left_price + fraction * (right_price - left_price)

    price_per_pixel = abs(
        (config.end_price - config.start_price) / (end_y - start_y)
    )
    errors: list[float] = []
    for x, ys in candidates.items():
        if max(ys) - min(ys) > 12:
            continue
        price = reconstructed_price(x)
        fraction = (price - config.start_price) / (
            config.end_price - config.start_price
        )
        estimated_y = start_y - fraction * (start_y - end_y)
        errors.append(abs(estimated_y - centerline[x]) * price_per_pixel)
    return {
        "mean_absolute_error": statistics.fmean(errors),
        "p95_absolute_error": _percentile(errors, 0.95),
        "max_absolute_error": max(errors),
        "clean_pixel_columns": float(len(errors)),
    }


def reference_metrics(
    reference_csv: Path,
    model: str,
    estimates: list[tuple[date, float]],
) -> dict[str, float] | None:
    if not reference_csv.exists():
        return None
    with reference_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    references = {
        date.fromisoformat(row["price_date"]): float(row["price_gpu_hour"])
        for row in rows
        if row["publisher_name"] == "Silicon Data"
        and row["gpu_model_code"] == model
        and row["price_gpu_hour"]
    }
    estimated = dict(estimates)
    errors = [
        abs(estimated[current_date] - price)
        for current_date, price in references.items()
        if current_date in estimated
    ]
    if not errors:
        return None
    return {
        "days": float(len(errors)),
        "mean_absolute_error": statistics.fmean(errors),
        "p95_absolute_error": _percentile(errors, 0.95),
        "max_absolute_error": max(errors),
    }


def write_estimates_csv(
    path: Path,
    all_estimates: dict[str, list[tuple[date, float]]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "price_date",
                "gpu_model_code",
                "estimated_price_gpu_hour",
                "currency",
                "precision",
                "estimate_method",
            ]
        )
        for model, estimates in all_estimates.items():
            for current_date, price in estimates:
                writer.writerow(
                    [
                        current_date.isoformat(),
                        model,
                        f"{price:.2f}",
                        "USD",
                        "0.01",
                        "digitized_from_silicon_data_curve",
                    ]
                )


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_provider_series_sql(
    path: Path,
    all_estimates: dict[str, list[tuple[date, float]]],
    *,
    run_date: date,
) -> None:
    rows = sorted(
        (
            current_date,
            model,
            price,
        )
        for model, estimates in all_estimates.items()
        for current_date, price in estimates
    )
    start_date = rows[0][0]
    end_date = rows[-1][0]
    models = sorted(all_estimates)
    chunks = [
        "BEGIN;",
        "",
        f"DELETE FROM {PROVIDER_SERIES_TABLE}",
        f"WHERE source_label = {_sql_string(SOURCE_LABEL)}",
        "  AND provider_id = 'silicondata'",
        "  AND billing_type = 'ON_DEMAND'",
        "  AND term_months = 0",
        "  AND gpu_model_code IN ("
        + ",".join(_sql_string(model) for model in models)
        + ")",
        f"  AND price_date BETWEEN '{start_date}' AND '{end_date}';",
        "",
    ]
    columns = ",".join(PROVIDER_SERIES_COLUMNS)
    for batch_start in range(0, len(rows), 500):
        values = []
        for current_date, model, price in rows[batch_start : batch_start + 500]:
            values.append(
                "    ("
                + ",".join(
                    [
                        _sql_string(current_date.isoformat()),
                        _sql_string(run_date.isoformat()),
                        _sql_string(GPU_IDS[model]),
                        _sql_string(model),
                        "'ON_DEMAND'",
                        "0",
                        "'silicondata'",
                        f"{price:.2f}",
                        "1",
                        "'GPU Cloud'",
                        _sql_string(REFERENCE_URL),
                        _sql_string(SOURCE_LABEL),
                    ]
                )
                + ")"
            )
        chunks.extend(
            [
                f"INSERT INTO {PROVIDER_SERIES_TABLE} ({columns}) VALUES",
                ",\n".join(values) + ";",
                "",
            ]
        )
    chunks.append("COMMIT;")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def _month_starts(start: date, end: date) -> list[date]:
    current = start.replace(day=1)
    values: list[date] = []
    while current <= end:
        values.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return values


def write_estimate_plot_svg(
    path: Path,
    all_estimates: dict[str, list[tuple[date, float]]],
) -> None:
    width = 1600
    height = 900
    left = 110
    right = 45
    top = 95
    bottom = 100
    plot_width = width - left - right
    plot_height = height - top - bottom
    start = min(values[0][0] for values in all_estimates.values())
    end = max(values[-1][0] for values in all_estimates.values())
    total_days = (end - start).days
    y_min = 2.5
    y_max = 8.0
    colors = {"B300": "#e11d48", "B200": "#2e63e6", "H200": "#059669"}

    def x_position(value: date) -> float:
        return left + ((value - start).days / total_days) * plot_width

    def y_position(value: float) -> float:
        return top + ((y_max - value) / (y_max - y_min)) * plot_height

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="110" y="45" font-family="Arial, sans-serif" font-size="30" '
        'font-weight="700" fill="#0f172a">Silicon Data estimated daily GPU '
        "index prices</text>",
        '<text x="110" y="75" font-family="Arial, sans-serif" font-size="16" '
        'fill="#475569">Digitized from the supplied curves; USD per GPU-hour, '
        "rounded to $0.01</text>",
    ]
    tick = y_min
    while tick <= y_max + 1e-9:
        y = y_position(tick)
        parts.extend(
            [
                f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" '
                f'y2="{y:.2f}" stroke="#e2e8f0" stroke-width="1"/>',
                f'<text x="{left - 18}" y="{y + 6:.2f}" text-anchor="end" '
                'font-family="Arial, sans-serif" font-size="15" '
                f'fill="#64748b">${tick:.2f}</text>',
            ]
        )
        tick += 0.5
    for month_index, month in enumerate(_month_starts(start, end)):
        if month_index % 2:
            continue
        x = x_position(month)
        parts.extend(
            [
                f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
                f'y2="{height - bottom}" stroke="#f1f5f9" stroke-width="1"/>',
                f'<text x="{x:.2f}" y="{height - bottom + 35}" '
                'text-anchor="middle" font-family="Arial, sans-serif" '
                f'font-size="14" fill="#64748b">{month:%b %Y}</text>',
            ]
        )
    for model, estimates in all_estimates.items():
        points = " ".join(
            f"{x_position(current_date):.2f},{y_position(price):.2f}"
            for current_date, price in estimates
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{colors[model]}" '
            'stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
        )
    legend_x = 1030
    for index, model in enumerate(("B300", "B200", "H200")):
        x = legend_x + index * 155
        parts.extend(
            [
                f'<line x1="{x}" y1="58" x2="{x + 34}" y2="58" '
                f'stroke="{colors[model]}" stroke-width="5"/>',
                f'<text x="{x + 44}" y="64" font-family="Arial, sans-serif" '
                f'font-size="17" fill="#1e293b">{model}</text>',
            ]
        )
    parts.extend(
        [
            f'<line x1="{left}" y1="{height - bottom}" '
            f'x2="{width - right}" y2="{height - bottom}" '
            'stroke="#94a3b8" stroke-width="1"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" '
            f'y2="{height - bottom}" stroke="#94a3b8" stroke-width="1"/>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_quality_report(
    path: Path,
    curve_metrics: dict[str, dict[str, float]],
    historical_metrics: dict[str, dict[str, float] | None],
) -> None:
    lines = [
        "# Silicon Data curve digitization quality",
        "",
        "The source line is isolated by its exact rendered RGB value, sampled at "
        "each calendar date, calibrated to the labeled start/end prices, clamped "
        "to the labeled period extrema, and rounded to $0.01.",
        "",
        "## Reconstruction against source-image pixels",
        "",
        "| GPU | Clean columns | Mean absolute error | P95 error | Max error |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, metrics in curve_metrics.items():
        lines.append(
            f"| {model} | {int(metrics['clean_pixel_columns']):,} | "
            f"${metrics['mean_absolute_error']:.4f} | "
            f"${metrics['p95_absolute_error']:.4f} | "
            f"${metrics['max_absolute_error']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Columns obscured by the chart's high/low annotation markers are "
            "interpolated and excluded from the pixel-error metric.",
            "The isolated maximum residuals occur at near-vertical joins between "
            "calendar samples; the mean and p95 values describe the visible "
            "trace more reliably.",
            "",
            "## Cross-check against saved October 1–November 8 observations",
            "",
            "| GPU | Days | Mean absolute error | P95 error | Max error |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for model, metrics in historical_metrics.items():
        if metrics is None:
            lines.append(f"| {model} | 0 | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {model} | {int(metrics['days'])} | "
            f"${metrics['mean_absolute_error']:.4f} | "
            f"${metrics['p95_absolute_error']:.4f} | "
            f"${metrics['max_absolute_error']:.4f} |"
        )
    lines.extend(
        [
            "",
            "The comparison PNGs draw the reconstructed, two-decimal series in "
            "magenta over the supplied blue source curves. Visible blue outside "
            "the magenta trace identifies a mismatch.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Digitize daily Silicon Data prices from supplied chart screenshots."
        )
    )
    parser.add_argument("--images-dir", type=Path, default=Path("images"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/silicondata_estimates"),
    )
    parser.add_argument(
        "--reference-csv",
        type=Path,
        default=Path("output/gpu_prices_history_20261001_20261108.csv"),
    )
    parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path(
            "sql/warehouse/"
            "05_insert_silicondata_gpu_index_provider_series_daily.sql"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_estimates: dict[str, list[tuple[date, float]]] = {}
    curve_metrics: dict[str, dict[str, float]] = {}
    historical_metrics: dict[str, dict[str, float] | None] = {}

    for config in CONFIGS:
        image_path = args.images_dir / config.image_name
        raster = read_png(image_path)
        centerline, candidates = extract_centerline(raster)
        estimates, start_y, end_y = estimate_curve(config, centerline)
        all_estimates[config.model] = estimates
        curve_metrics[config.model] = reconstruction_metrics(
            config,
            estimates,
            start_y,
            end_y,
            centerline,
            candidates,
        )
        historical_metrics[config.model] = reference_metrics(
            args.reference_csv,
            config.model,
            estimates,
        )
        comparison_path = (
            args.output_dir
            / f"silicondata_{config.model.lower()}_curve_comparison.png"
        )
        write_comparison_png(
            comparison_path,
            raster,
            config,
            estimates,
            start_y,
            end_y,
        )

    csv_path = args.output_dir / "silicondata_estimated_daily_prices.csv"
    plot_path = args.output_dir / "silicondata_estimated_price_curves.svg"
    report_path = args.output_dir / "quality_report.md"
    write_estimates_csv(csv_path, all_estimates)
    write_estimate_plot_svg(plot_path, all_estimates)
    write_quality_report(
        report_path,
        curve_metrics,
        historical_metrics,
    )
    run_date = max(config.end_date for config in CONFIGS)
    write_provider_series_sql(
        args.sql_path,
        all_estimates,
        run_date=run_date,
    )

    print(f"Estimated rows: {sum(map(len, all_estimates.values())):,}")
    print(csv_path)
    print(plot_path)
    print(report_path)
    print(args.sql_path)
    for model in all_estimates:
        image_error = curve_metrics[model]["mean_absolute_error"]
        reference = historical_metrics[model]
        reference_error = (
            "n/a"
            if reference is None
            else f"${reference['mean_absolute_error']:.4f}"
        )
        print(
            f"{model}: source-pixel MAE=${image_error:.4f}, "
            f"saved-history MAE={reference_error}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
