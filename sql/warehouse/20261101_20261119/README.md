# November 1–19 warehouse load

Run in this order:

1. `../12_insert_amd_gpu_providers.sql`
2. `13_insert_compute_insight_gpu_price_detail_daily.sql`
3. `14_insert_compute_insight_gpu_provider_series_daily.sql`
4. `15_insert_compute_insight_gpu_price_series_daily.sql`

Coverage:

- Existing non-AMD raw data from November 1–8 is retained in the replacement
  window.
- New non-AMD prices cover November 9–19. Published curves use their dated
  online values; static pages carry the November 19 value backward.
- AMD prices cover November 1–19 and use the November 19 static list price.
- GPUBank was unreachable on November 19, so its November 17 values are carried
  as `UNAVAILABLE` with an explicit stale-value note.
- AWS Capacity Block reservation terms are normalized to six months.
- `GPU INDEX` replacement begins November 9, preserving previously loaded H100
  index history before that date.

Row counts:

- Detail: 3,767
- Provider series SQL: 3,039
- Price series: 2,240
