-- A new empty tenant graph needs the current snapshot, not every historical event.
-- Resuming an existing graph still replays every event after its committed watermark.

CREATE OR REPLACE FUNCTION stackgraph_backfill_graph_projection_deployment()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  maximum_outbox_id bigint;
BEGIN
  IF NEW.deployment_state<>'ACTIVE'
     OR (TG_OP='UPDATE' AND OLD.deployment_state='ACTIVE') THEN
    RETURN NEW;
  END IF;

  IF NEW.projected_outbox_id=0 THEN
    WITH applicable AS MATERIALIZED (
      SELECT outbox.id
      FROM projection_outbox outbox
      JOIN fact_assertion fact ON fact.id=outbox.aggregate_id
      WHERE outbox.aggregate_type='FACT'
        AND outbox.operation='UPSERT'
        AND fact.system_to IS NULL
        AND (outbox.tenant_id IS NULL OR outbox.tenant_id=NEW.tenant_id)
      UNION
      SELECT max(outbox.id)
      FROM projection_outbox outbox
      WHERE outbox.aggregate_type='FACT'
        AND (outbox.tenant_id IS NULL OR outbox.tenant_id=NEW.tenant_id)
      HAVING max(outbox.id) IS NOT NULL
    )
    INSERT INTO graph_projection_delivery(outbox_id,tenant_id,deployment_id)
    SELECT applicable.id,NEW.tenant_id,NEW.id
    FROM applicable
    ON CONFLICT(outbox_id,tenant_id) DO NOTHING;
  ELSE
    INSERT INTO graph_projection_delivery(outbox_id,tenant_id,deployment_id)
    SELECT outbox.id,NEW.tenant_id,NEW.id
    FROM projection_outbox outbox
    WHERE outbox.aggregate_type='FACT'
      AND outbox.id>NEW.projected_outbox_id
      AND (outbox.tenant_id IS NULL OR outbox.tenant_id=NEW.tenant_id)
    ON CONFLICT(outbox_id,tenant_id) DO NOTHING;
  END IF;

  SELECT coalesce(max(delivery.outbox_id),NEW.projected_outbox_id)
  INTO maximum_outbox_id
  FROM graph_projection_delivery delivery
  WHERE delivery.deployment_id=NEW.id;

  UPDATE tenant_graph_deployment
  SET desired_outbox_id=greatest(desired_outbox_id,maximum_outbox_id),
      updated_at=now()
  WHERE id=NEW.id;

  RETURN NEW;
END
$$;
