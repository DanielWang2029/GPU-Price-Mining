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

- `gpu_prices_YYYYMMDD.csv`: the seven database columns from `表结构设计`.
- `gpu_prices_YYYYMMDD.xlsx`: the same rows as an Excel table.
- `gpu_prices_YYYYMMDD_audit.csv`: source row, status, source URL, effective time,
  raw value, and collection note.

`price` is blank only when the supplier currently does not publish or offer that
exact row. This is `status=unavailable` in the audit file. Fetch, schema, and parse
failures are `status=error`; `--strict` makes those failures return a nonzero exit
code, which is suitable for Airflow. An unavailable product does not fail the job
and is never replaced with zero or an old value.

Workbook values are trimmed before matching, fixing the leading spaces currently
present on several A100 and Community rows.

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
| Together.ai | GPU cluster table; Reserve means the marked 91–180 day column and Spot means Preemptible. |
| Daytona | Current on-demand/preemptible panels. A removed model is emitted as unavailable. |
| UpCloud | Authenticated catalog when `UPCLOUD_TOKEN` is set; otherwise the public global USD one-GPU table. |
| Gpu.ai | Documented public catalog; lowest available secure on-demand per-GPU price. |
| Spheron | Public offer feed; lowest available Dedicated or Spot offer normalized by GPU count. |
| Hyperbolic | Advertised marketplace “Starting From” table, which the source refreshes weekly. |
| DeepInfra | Custom LLM dedicated GPU table, not token inference pricing. |
| Fireworks.ai | Public pricing CMS, hourly on-demand deployment column. |
| Astra Intellectus | Lowest visible static indicative offer. Hidden stale tables are ignored; client-side randomized prices are intentionally not ingested. |
| Verda | Exact public one-GPU SKU from the instance catalog, using on-demand or spot price. |

### Anti-bot fallback

Kalshi, GetDeploying, and UpCloud may reject datacenter IPs even though their data
is public. Prefer running from an allowed network or using the suppliers'
authenticated API where supported. For a one-off collection, the command can use
a public read-only text proxy:

```bash
python3 -m gpu_prices.collect --allow-read-proxy --strict
```

The audit file records when this fallback was used. It never sends API tokens to
the proxy. The same setting can be enabled with
`GPU_PRICES_ALLOW_READ_PROXY=true`.

## Airflow

Scheduling is intentionally not included. A task can invoke:

```bash
python3 -m gpu_prices.collect \
  --workbook /path/to/算力价格爬虫数据整理.xlsx \
  --output-dir /path/to/daily-output \
  --run-date '{{ ds_nodash }}' \
  --strict
```

Persist the audit file with the database load so source changes and unavailable
products remain distinguishable from valid numeric prices.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
