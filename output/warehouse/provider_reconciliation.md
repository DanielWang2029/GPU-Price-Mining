# Price mining warehouse reconciliation

## Provider IDs merged

- `Astra Intellectus`: `astraintellectus` → `astra-intellectus`
- `Cyfuture.ai`: `cyfutureai` → `cyfuture`
- `Fireworks.ai`: `fireworksai` → `fireworks-ai`
- `Gpu.ai`: `gpuai` → `gpu-ai`
- `Impossible Cloud`: `impossiblecloud` → `impossible-cloud`
- `Latitude.sh`: `latitudesh` → `latitude-sh`
- `TheAI Cloud`: `theaicloud` → `theai-cloud`
- `Together.ai`: `togetherai` → `together-ai`

## Providers inserted into dim_provider

- `astra-intellectus` — Astra Intellectus; MY/Asia-Pacific; GPU Cloud
- `ccir` — CCIR; US/North America; Serverless
- `deepinfra` — DeepInfra; US/North America; GPU Cloud
- `fireworks-ai` — Fireworks AI; US/North America; GPU Cloud
- `getdeploying` — GetDeploying; DE/Europe; Serverless
- `kalshi` — Kalshi; US/North America; Serverless
- `ornn` — Ornn; US/North America; Serverless
- `silicondata` — Silicon Data; US/North America; GPU Cloud

## Main transformations

- Raw price-mining rows are loaded into `compute_insight_gpu_price_detail_daily`; this follows the workbook schema (the request had the raw/aggregate table names reversed).
- Existing dim_provider IDs, names, supplier types, and missing HQ geography are applied before aggregation.
- Blank index-series billing types are normalized to `SPOT`, the non-null warehouse category for market/index rates.
- Aggregate tables include only priced records with a nonblank term.
- Provider medians group by date, GPU model, provider, billing type, and term.
- Price percentiles group by date, GPU model, billing type, term, supplier type, and region.
- Percentile fields use continuous p25/p50/p75; `min_price` is the minimum (p0), matching the target schema.
- Detail rows: 655.
- Provider-series rows: 100.
- Price-series rows: 100.
- Duplicate record IDs under the requested MD5 formula: 0.
