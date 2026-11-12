BEGIN;

DELETE FROM public.compute_insight_gpu_price_detail_daily
WHERE source_label = 'price_mining'
  AND (
    provider_id IN ('silicondata', 'ornn', 'compute-desk', 'computedesk')
    OR publisher_name IN ('SiliconData', 'Silicon Data', 'Ornn', 'Compute Desk')
  );

COMMIT;
