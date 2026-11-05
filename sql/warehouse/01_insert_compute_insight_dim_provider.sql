INSERT INTO public.compute_insight_dim_provider (provider_id,provider_name,website,region_or_hq_country,provider_hq_region,supplier_type,tier_confidence,updated_at)
SELECT v.*
FROM (VALUES
    ('astra-intellectus','Astra Intellectus','https://astra-intellectus.com','MY','Asia-Pacific','GPU Cloud','review','2026-11-03 00:00:00'),
    ('ccir','CCIR','https://ccir.io','US','North America','Serverless','review','2026-11-03 00:00:00'),
    ('deepinfra','DeepInfra','https://deepinfra.com','US','North America','GPU Cloud','review','2026-11-03 00:00:00'),
    ('fireworks-ai','Fireworks AI','https://fireworks.ai','US','North America','GPU Cloud','review','2026-11-03 00:00:00'),
    ('getdeploying','GetDeploying','https://getdeploying.com','DE','Europe','Serverless','review','2026-11-03 00:00:00'),
    ('kalshi','Kalshi','https://kalshi.com','US','North America','Serverless','review','2026-11-03 00:00:00'),
    ('ornn','Ornn','https://data.ornn.com','US','North America','Serverless','review','2026-11-03 00:00:00'),
    ('silicondata','Silicon Data','https://www.silicondata.com','US','North America','GPU Cloud','review','2026-11-03 00:00:00')
) AS v (provider_id,provider_name,website,region_or_hq_country,provider_hq_region,supplier_type,tier_confidence,updated_at)
WHERE NOT EXISTS (
    SELECT 1
    FROM public.compute_insight_dim_provider AS existing
    WHERE existing.provider_id = v.provider_id
);
