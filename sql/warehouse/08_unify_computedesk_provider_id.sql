BEGIN;

INSERT INTO public.compute_insight_dim_provider (
    provider_id,
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
)
SELECT
    'computedesk',
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
FROM public.compute_insight_dim_provider
WHERE provider_id = 'compute-desk'
  AND NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'computedesk'
  );

UPDATE public.compute_insight_gpu_price_detail_daily
SET
    provider_id = 'computedesk',
    record_id = md5(CONCAT_WS(
        ':',
        price_date,
        run_date,
        source_label,
        'computedesk',
        region_or_hq_country,
        provider_hq_region,
        gpu_id,
        billing_type,
        term_months,
        raw_price,
        price_gpu_hour,
        availability
    ))
WHERE provider_id = 'compute-desk';

UPDATE public.compute_insight_gpu_provider_series_daily
SET provider_id = 'computedesk'
WHERE provider_id = 'compute-desk';

DELETE FROM public.compute_insight_dim_provider
WHERE provider_id = 'compute-desk'
  AND EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'computedesk'
  );

COMMIT;
