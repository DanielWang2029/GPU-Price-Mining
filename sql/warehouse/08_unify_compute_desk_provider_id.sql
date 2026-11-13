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
    'compute-desk',
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
FROM public.compute_insight_dim_provider
WHERE provider_id = 'computedesk'
  AND NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'compute-desk'
  );

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
    'compute-desk',
    'Compute Desk',
    'https://www.computedesk.com',
    'US',
    'North America',
    'Serverless',
    'review',
    LOCALTIMESTAMP
WHERE NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'compute-desk'
);

WITH remapped AS (
    SELECT
        record_id AS old_record_id,
        md5(CONCAT_WS(
            ':',
            price_date,
            run_date,
            source_label,
            'compute-desk',
            region_or_hq_country,
            provider_hq_region,
            gpu_id,
            billing_type,
            term_months,
            raw_price,
            price_gpu_hour,
            availability
        )) AS canonical_record_id
    FROM public.compute_insight_gpu_price_detail_daily
    WHERE provider_id = 'computedesk'
)
DELETE FROM public.compute_insight_gpu_price_detail_daily AS alias
USING remapped
WHERE alias.record_id = remapped.old_record_id
  AND EXISTS (
    SELECT 1
    FROM public.compute_insight_gpu_price_detail_daily AS canonical
    WHERE canonical.record_id = remapped.canonical_record_id
  );

UPDATE public.compute_insight_gpu_price_detail_daily
SET
    provider_id = 'compute-desk',
    record_id = md5(CONCAT_WS(
        ':',
        price_date,
        run_date,
        source_label,
        'compute-desk',
        region_or_hq_country,
        provider_hq_region,
        gpu_id,
        billing_type,
        term_months,
        raw_price,
        price_gpu_hour,
        availability
    ))
WHERE provider_id = 'computedesk';

DELETE FROM public.compute_insight_gpu_provider_series_daily AS alias
USING public.compute_insight_gpu_provider_series_daily AS canonical
WHERE alias.provider_id = 'computedesk'
  AND canonical.provider_id = 'compute-desk'
  AND canonical.price_date = alias.price_date
  AND canonical.gpu_id IS NOT DISTINCT FROM alias.gpu_id
  AND canonical.gpu_model_code IS NOT DISTINCT FROM alias.gpu_model_code
  AND canonical.billing_type = alias.billing_type
  AND canonical.term_months = alias.term_months
  AND canonical.source_label = alias.source_label;

UPDATE public.compute_insight_gpu_provider_series_daily
SET provider_id = 'compute-desk'
WHERE provider_id = 'computedesk';

DELETE FROM public.compute_insight_dim_provider
WHERE provider_id = 'computedesk'
  AND EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'compute-desk'
  );

COMMIT;
