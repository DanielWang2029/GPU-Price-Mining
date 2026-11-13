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
    'silicondata',
    'Silicon Data',
    'https://www.silicondata.com',
    'US',
    'North America',
    'GPU Cloud',
    'review',
    LOCALTIMESTAMP
WHERE NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider
    WHERE provider_id = 'silicondata'
);

UPDATE public.compute_insight_dim_provider
SET provider_name = 'Silicon Data'
WHERE provider_id = 'silicondata'
  AND provider_name IS DISTINCT FROM 'Silicon Data';

UPDATE public.compute_insight_gpu_price_detail_daily
SET publisher_name = 'Silicon Data'
WHERE publisher_name = 'SiliconData';

COMMIT;
