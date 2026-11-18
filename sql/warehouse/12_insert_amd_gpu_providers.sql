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
    ('bentaus','Bentaus','https://www.bentaus.com','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('cirrascale','Cirrascale','https://www.cirrascale.com','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('coregpu','CoreGPU','https://coregpu.io','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('cyfuture','Cyfuture AI','https://cyfuture.ai','IN','Asia-Pacific','GPU Cloud','review','2026-11-17 00:00:00'),
    ('daytona','Daytona','https://www.daytona.io','US','North America','Serverless','review','2026-11-17 00:00:00'),
    ('digitalocean','DigitalOcean','https://www.digitalocean.com','US','North America','General Cloud & Hosting','review','2026-11-17 00:00:00'),
    ('gpubank','GPUBank','https://gpubank.io',NULL,NULL,'Unclassified','low','2026-11-17 00:00:00'),
    ('hotaisle','Hot Aisle','https://hotaisle.xyz','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('impossible-cloud','Impossible Cloud','https://www.impossiblecloud.com','DE','Europe','General Cloud & Hosting','review','2026-11-17 00:00:00'),
    ('microsoft-azure','Microsoft Azure','https://azure.microsoft.com','US','North America','Hyperscaler','review','2026-11-17 00:00:00'),
    ('openrelay','OpenRelay','https://openrelay.inc','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('oracle-cloud','Oracle Cloud','https://www.oracle.com/cloud','US','North America','Hyperscaler','review','2026-11-17 00:00:00'),
    ('runcrate','Runcrate','https://www.runcrate.ai','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('runpod','Runpod','https://www.runpod.io','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('tensorwave','TensorWave','https://tensorwave.com','US','North America','GPU Cloud','review','2026-11-17 00:00:00'),
    ('vultr','Vultr','https://www.vultr.com','US','North America','General Cloud & Hosting','review','2026-11-17 00:00:00')
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
