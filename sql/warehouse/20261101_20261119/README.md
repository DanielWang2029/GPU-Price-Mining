# 2026-11-01–2026-11-19 warehouse load

Run in this order:

1. `../12_insert_amd_gpu_providers.sql`
2. `13_insert_compute_insight_gpu_price_detail_daily.sql`
3. `14_insert_compute_insight_gpu_provider_series_daily.sql`
4. `15_insert_compute_insight_gpu_price_series_daily.sql`

Only `coregpu` and `gpubank` are absent from the supplied provider dimension;
SQL 12 contains only those two IDs.

`price_mining` is replaced from 2026-11-01 through 2026-11-19.
`GPU INDEX` is replaced only from 2026-11-09 through
2026-11-19, preserving earlier index history. GPUBank's last known prices
are marked unavailable because its source was unreachable at the end date.

Row counts:

- Detail: 3,767
- Provider series SQL: 3,039
- Price series: 2,297
