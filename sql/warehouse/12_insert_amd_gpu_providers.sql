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
    values.provider_id,
    values.provider_name,
    values.website,
    values.region_or_hq_country,
    values.provider_hq_region,
    values.supplier_type,
    values.tier_confidence,
    values.updated_at::timestamp without time zone
FROM (VALUES
    ('coregpu','CoreGPU','https://coregpu.io','US','North America','GPU Cloud','review','2026-11-19 00:00:00'),
    ('gpubank','GPUBank','https://gpubank.io',NULL,NULL,'Unclassified','low','2026-11-19 00:00:00')
) AS values (
    provider_id,
    provider_name,
    website,
    region_or_hq_country,
    provider_hq_region,
    supplier_type,
    tier_confidence,
    updated_at
)
WHERE NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider AS existing
    WHERE existing.provider_id = values.provider_id
);
