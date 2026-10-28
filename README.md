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
  --run-date 20261021 \
  --strict
```

## Outputs

Each run writes:

- `gpu_prices_YYYYMMDD.csv`: the eleven database columns from `表结构设计`.
- `gpu_prices_YYYYMMDD.xlsx`: the same rows as an Excel table.
- `gpu_prices_YYYYMMDD_audit.csv`: source row, status, source URL, effective time,
  raw value, and collection note.

`price` is blank only when the supplier currently does not publish or offer that
exact row. This is `status=unavailable` in the audit file. Fetch, schema, and parse
failures are `status=error`; `--strict` makes those failures return a nonzero exit
code, which is suitable for Airflow. An unavailable product does not fail the job
and is never replaced with zero or an old value.

Workbook values are trimmed before matching, fixing the leading spaces currently
present on several A100 and Community rows. Every generated row sets
`data_source` to `price_mining`.

## Source behavior

| Supplier | Collection source and workbook interpretation |
| --- | --- |
| Kalshi | Public forward-curve JSON; evaluates the log-PCHIP chart curve at collection time. |
| Ornn | Settled global daily index API. |
| CoreWeave | North America HTML table. The red boxes are whole-instance prices, so the values are deliberately not divided by GPU count. |
| SiliconData | Structured Neo-Cloud index data embedded in each public product page. |
| Nebius | Structured standard-price page data plus the public current spot-price API with explicit region mapping. |
| GetDeploying | Latest weekly provider-median values in the page's Price history summary. |
| RunPod | Public GraphQL catalog; A100 means A100 80GB PCIe, matching the screenshot. |
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
| Civo | GPU tables with multi-GPU node prices normalized per GPU. |
| Cyfuture.ai | INR B300 rates converted with the current Frankfurter USD/INR reference rate. |
| Latitude.sh | Embedded B300 plan data, normalized from monthly/yearly eight-GPU node prices. |
| AWS | Capacity Block per-accelerator prices plus current us-east-1 Linux Spot prices divided by eight. |

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
  --end-date 20261028 \
  --current-csv output/gpu_prices_20261028.csv \
  --allow-read-proxy
```

The output defaults to
`output/gpu_prices_history_20261001_20261028.csv`. The command also writes
`sql/t_gpu_daily_prices.sql`, containing the unconstrained PostgreSQL table
definition and direct values for every historical row. Historical sources are:

- Kalshi's realized history plus its currently published forward curve,
  evaluated daily at 20:00 UTC.
- Ornn's settled daily index history.
- Silicon Data's explicit daily chart points.
- Nebius spot-price 15-minute history, sampled at the DAG's 9:00 PM
  `America/Los_Angeles` cutoff.
- GetDeploying's weekly chart dataset, carried forward through each week. Its
  generic Reserve value is the offering-count-weighted median used by the
  online chart.

All other rows have no published curve and therefore carry the end-date price
back across the requested range. The backfill fails rather than inventing a
value if any curve-based source omits a requested date.

Kalshi does not expose archived point-in-time forward-curve snapshots. Its past
dates can be evaluated on the curve published today, but the exact curve that
users saw on a prior day cannot be reconstructed retroactively.

## Airflow

`dags/gpu_prices_daily.py` runs all suppliers every day at 9:00 PM in
`America/Los_Angeles`. The DAG uses the local data-interval end for
`dtstatdate`, so an Airflow scheduler running in UTC does not write the next
day's date early.

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
