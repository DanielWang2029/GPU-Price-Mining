# GPU Price Mining

Python collectors for every row in `算力价格爬虫数据整理.xlsx`. Supplier logic is
split into one module per supplier under `src/gpu_prices/providers/`.

## Run

```bash
python3 -m pip install -e .
python3 -m gpu_prices.collect --strict
```

The default input is `算力价格爬虫数据整理.xlsx`, and the default output directory is
`output/`. To run one supplier only:

```bash
python3 -m gpu_prices.providers.ornn --output-dir output/ornn --strict
python3 -m gpu_prices.providers.nebius --output-dir output/nebius --strict
```

The top-level command also accepts repeatable supplier filters:

```bash
python3 -m gpu_prices.collect \
  --provider Ornn \
  --provider Nebius \
  --price-date 20261021 \
  --run-date 20261022 \
  --strict
```

`price_date` is the date associated with the price. `run_date` is the local date
on which the record was collected; both default to the current
`America/Los_Angeles` date.

## Outputs

Each run writes:

- `gpu_prices_YYYYMMDD.csv`: the 27 database columns from `表结构设计`.
- `gpu_prices_YYYYMMDD.xlsx`: the same rows as an Excel table.
- `gpu_prices_YYYYMMDD_audit.csv`: source row, status, source URL, effective time,
  raw value, and collection note.

`raw_price` is the total amount published for the selected offering and
`price_gpu_hour` is its normalized one-GPU hourly price. `gpu_count` records the
number of GPUs covered by the raw amount. The two prices are normally equal, but
multi-GPU instances retain their total price and count. `availability` is
`AVAILABLE` unless the source explicitly reports that the offering is unavailable
or waitlisted.

Prices are blank only when the supplier currently does not publish or offer that
exact row. This is `availability=UNAVAILABLE` and `status=unavailable` in the audit
file. Fetch, schema, and parse failures are `status=error`; `--strict` makes those
failures return a nonzero exit code, which is suitable for Airflow. An unavailable
product does not fail the job and is never replaced with zero or an old value.

Workbook values are trimmed before matching. Empty values remain empty rather
than being replaced with `N/A`. Every generated row sets `source_label` to
`price_mining`, derives a letters-only lowercase `provider_id`, and leaves the
reserved enrichment and note columns blank.

`record_id` is the lowercase MD5 hex digest of the colon-separated
`price_date`, `run_date`, `source_label`, `provider_id`, `gpu_id`,
`billing_type`, `term_months`, `raw_price`, `price_gpu_hour`, and
`availability` output values. Null/blank database fields are skipped to match
PostgreSQL `CONCAT_WS` semantics.

## Source behavior

| Supplier | Collection source and workbook interpretation |
| --- | --- |
| Kalshi | Public forward-curve JSON; evaluates the log-PCHIP chart curve at collection time. |
| Ornn | Settled global daily index API. |
| CoreWeave | North America HTML table. Whole-instance totals and GPU counts are retained, then normalized per GPU. |
| SiliconData | Structured Neo-Cloud index data embedded in each public product page. |
| Nebius | Structured standard-price page data plus the public current spot-price API with explicit region mapping. |
| GetDeploying | Latest weekly provider-median values in the page's Price history summary. |
| RunPod | Public GraphQL Secure Cloud catalog; A100 means A100 80GB PCIe. |
| Together.ai | GPU cluster table; reserve terms 1/3/6 map to the 3–30, 31–90, and 91–180 day columns. |
| Daytona | Complete on-demand/preemptible panel, cross-checked against GetDeploying's provider-specific listing because Daytona's server-rendered B300 cell currently duplicates the B200 price. |
| UpCloud | Authenticated catalog when `UPCLOUD_TOKEN` is set; otherwise the public global USD one-GPU table. |
| Gpu.ai | Documented public catalog; lowest available secure on-demand per-GPU price. |
| Spheron | Public offer feed; lowest available Dedicated or Spot offer normalized by GPU count. |
| Hyperbolic | Advertised marketplace “Starting From” table, which the source refreshes weekly. |
| DeepInfra | Custom LLM dedicated GPU table, not token inference pricing. |
| Fireworks.ai | Public pricing CMS, hourly on-demand deployment column. |
| Astra Intellectus | Lowest visible static indicative offer. Hidden stale tables are ignored; client-side randomized prices are intentionally not ingested. |
| Verda | Exact public one-GPU SKU from the instance catalog, using on-demand or spot price. |
| Impossible Cloud | First page-order model card with numeric GPU capacity; validates selected region and term. |
| TheAI Cloud | Public pricing API. Workbook H200 labels are normalized to B300 because the supplier discontinued H200 and the screenshots show B300. |
| Digital Ocean | Reserved, spot, and on-demand GPU pricing cards. |
| Bentaus | Lower bound of the advertised B300 per-GPU price range. |
| Civo | GPU tables with raw multi-GPU node prices, GPU counts, and normalized per-GPU prices. |
| Cyfuture.ai | INR B300 rates converted with the current Frankfurter USD/INR reference rate. |
| Latitude.sh | Embedded B300 plan data, retaining monthly/yearly eight-GPU node totals and normalizing them per GPU-hour. |
| AWS | Capacity Block and current us-east-1 Linux Spot instance totals with per-GPU normalization (8 GPUs for B200/B300 and 72 for GB200). |
| Hyperstack | Server-rendered on-demand/reservation rates plus the official live stock mirror for availability. |
| CCIR | Embedded zone-level spot curves; rates are already quoted per GPU-hour. |

### Anti-bot fallback

Kalshi, GetDeploying, UpCloud, and Cyfuture may reject datacenter IPs even though their data
is public. Prefer running from an allowed network or using the suppliers'
authenticated API where supported. For a one-off collection, the command can use
a public read-only text proxy:

```bash
python3 -m gpu_prices.collect --allow-read-proxy --strict
```

The audit file records when this fallback was used. It never sends API tokens to
the proxy. The same setting can be enabled with
`GPU_PRICES_ALLOW_READ_PROXY=true`.

## Historical backfill

`gpu_prices.backfill` creates one row per workbook price and calendar date.

```bash
python3 -m gpu_prices.backfill \
  --start-date 20261001 \
  --end-date 20261103 \
  --run-date 20261103 \
  --current-csv output/gpu_prices_20261103.csv \
  --prior-history output/gpu_prices_history_20261001_20261103.csv \
  --allow-read-proxy
```

The output defaults to
`output/gpu_prices_history_20261001_20261103.csv`. Historical sources are:

When extending beyond a source's rolling retention window, pass the latest
existing history file with `--prior-history`.

- Kalshi's realized history plus its currently published forward curve,
  evaluated daily at 20:00 UTC.
- Ornn's settled daily index history.
- Silicon Data's explicit daily chart points.
- Nebius spot-price 15-minute history, sampled at the DAG's 9:00 PM
  `America/Los_Angeles` cutoff.
- GetDeploying's weekly chart dataset, carried forward through each week. Its
  generic Reserve value is the offering-count-weighted median used by the
  online chart.
- CCIR's embedded daily zone curves, associated with the following day's
  9:00 PM Los Angeles collection cutoff. Dates before a selected zone existed
  remain `UNAVAILABLE` with blank prices.

All other rows have no published curve and therefore carry the end-date price
back across the requested range. The backfill fails rather than inventing a
value if any curve-based source omits a requested date.

Kalshi does not expose archived point-in-time forward-curve snapshots. Its past
dates can be evaluated on the curve published today, but the exact curve that
users saw on a prior day cannot be reconstructed retroactively.

## Warehouse loads

`gpu_prices.warehouse` reconciles the historical output against `tables.xlsx`,
applies canonical provider IDs and provider dimension metadata, calculates
daily provider medians and market percentiles, and emits direct-value SQL:

```bash
python3 -m gpu_prices.warehouse \
  --history-csv output/gpu_prices_history_20261001_20261103.csv \
  --tables-workbook tables.xlsx
```

The workbook schemas route raw rows to
`compute_insight_gpu_price_detail_daily`, provider medians to
`compute_insight_gpu_provider_series_daily`, and p25/p50/p75/min aggregates to
`compute_insight_gpu_price_series_daily`. Blank provider geography is filled
from `compute_insight_dim_provider`; existing provider IDs and classifications
take precedence over price-mining values.

Generated SQL is stored under `sql/warehouse/`, reconciled CSVs and the provider
merge/insert report under `output/warehouse/`.

## Airflow

`dags/gpu_prices_daily.py` runs all suppliers every day at 9:00 PM in
`America/Los_Angeles`. The DAG uses the local data-interval end for `price_date`
and records the task's actual local execution date separately as `run_date`.

Install this project and place or symlink the DAG into the Airflow DAG folder.
The scheduler and worker must see the same project, workbook, and output paths.
These environment variables can override the repository defaults:

- `GPU_PRICE_PROJECT_ROOT`: project checkout used as the task working directory.
- `GPU_PRICE_WORKBOOK`: absolute path to the source workbook.
- `GPU_PRICE_OUTPUT_DIR`: directory for the daily CSV, XLSX, and audit files.
- `GPU_PRICES_ALLOW_READ_PROXY`: defaults to `true` in the DAG because three
  public sources commonly block datacenter IPs.

The task retries twice, prevents overlapping DAG runs, disables historical
catchup, and uses `--strict` so collection errors fail the Airflow task.
Unavailable products remain valid null prices. Persist the audit file with the
database load so unavailable products remain distinguishable from failures.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
