-- Governed composite-risk weights. Policy content hashes remain the ranking provenance.

CREATE FUNCTION stackgraph_valid_risk_weights(configuration jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN NOT (configuration ? 'risk_weights') THEN true
    WHEN jsonb_typeof(configuration->'risk_weights')<>'object' THEN false
    WHEN jsonb_typeof(configuration->'risk_weights'->'families')<>'object' THEN false
    WHEN jsonb_typeof(configuration->'risk_weights'->'structural_metrics')<>'object' THEN false
    WHEN EXISTS (
      SELECT 1 FROM jsonb_each(configuration->'risk_weights'->'families') item
      WHERE jsonb_typeof(item.value)<>'number' OR (item.value#>>'{}')::numeric<0
    ) THEN false
    WHEN EXISTS (
      SELECT 1 FROM jsonb_each(configuration->'risk_weights'->'structural_metrics') item
      WHERE jsonb_typeof(item.value)<>'number' OR (item.value#>>'{}')::numeric<0
    ) THEN false
    ELSE (
      SELECT coalesce(sum((item.value#>>'{}')::numeric),0)>0
      FROM jsonb_each(configuration->'risk_weights'->'families') item
    ) AND (
      SELECT coalesce(sum((item.value#>>'{}')::numeric),0)>0
      FROM jsonb_each(configuration->'risk_weights'->'structural_metrics') item
    )
  END
$$;

ALTER TABLE graph_analysis_policy
  ADD CONSTRAINT graph_analysis_policy_valid_risk_weights
  CHECK(stackgraph_valid_risk_weights(configuration));

UPDATE graph_analysis_policy
SET status='RETIRED',retired_at=now()
WHERE tenant_id IS NULL AND policy_key='runtime-dependency' AND status='ACTIVE';

WITH current_policy AS (
  SELECT configuration
  FROM graph_analysis_policy
  WHERE tenant_id IS NULL AND policy_key='runtime-dependency'
  ORDER BY version DESC LIMIT 1
), prepared AS (
  SELECT jsonb_set(
    configuration,'{risk_weights}',
    '{
      "families":{"structural":0.40,"business":0.25,"exposure":0.25,"lifecycle":0.10},
      "structural_metrics":{"reachability.upstream_impact":0.40,"betweenness":0.30,"spof.articulation":0.20,"pagerank":0.10}
    }'::jsonb,true
  ) configuration
  FROM current_policy
)
INSERT INTO graph_analysis_policy(
  tenant_id,policy_key,version,name,status,configuration,content_hash,created_by,activated_at
)
SELECT NULL,'runtime-dependency',4,'Runtime dependency','ACTIVE',configuration,
       'sha256:'||encode(digest(configuration::text,'sha256'),'hex'),
       'migration:041',now()
FROM prepared;
