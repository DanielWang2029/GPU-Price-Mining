# Silicon Data curve digitization quality

The source line is isolated by its exact rendered RGB value, sampled at each calendar date, calibrated to the labeled start/end prices, clamped to the labeled period extrema, and rounded to $0.01.

## Reconstruction against source-image pixels

| GPU | Clean columns | Mean absolute error | P95 error | Max error |
|---|---:|---:|---:|---:|
| B300 | 2,386 | $0.0023 | $0.0090 | $0.0266 |
| B200 | 2,142 | $0.0038 | $0.0123 | $0.1100 |
| H200 | 2,331 | $0.0012 | $0.0040 | $0.0129 |

Columns obscured by the chart's high/low annotation markers are interpolated and excluded from the pixel-error metric.
The isolated maximum residuals occur at near-vertical joins between calendar samples; the mean and p95 values describe the visible trace more reliably.

## Cross-check against saved October 1–November 8 observations

| GPU | Days | Mean absolute error | P95 error | Max error |
|---|---:|---:|---:|---:|
| B300 | 39 | $0.0031 | $0.0100 | $0.0200 |
| B200 | 39 | $0.0167 | $0.0440 | $0.1100 |
| H200 | 39 | $0.0013 | $0.0100 | $0.0100 |

The comparison PNGs draw the reconstructed, two-decimal series in magenta over the supplied blue source curves. Visible blue outside the magenta trace identifies a mismatch.
