BEGIN;

DELETE FROM public.compute_insight_gpu_provider_series_daily
WHERE source_label = 'price_mining'
  AND provider_id IN ('silicondata', 'ornn', 'compute-desk', 'computedesk');

COMMIT;
