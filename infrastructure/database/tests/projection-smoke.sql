\set ON_ERROR_STOP on

DO $$
DECLARE
  relational_entity_count integer;
  graph_entity_count integer;
  relational_relationship_count integer;
  graph_relationship_count integer;
  missing_entity_count integer;
  missing_relationship_count integer;
  pending_projection_count integer;
BEGIN
  SELECT count(*) INTO relational_entity_count
  FROM entity
  WHERE tenant_id IS NULL;

  SELECT count(*) INTO graph_entity_count
  FROM stackgraph."Entity";

  SELECT count(*) INTO relational_relationship_count
  FROM current_relationship relationship
  JOIN fact_assertion fact ON fact.id = relationship.fact_assertion_id
  WHERE fact.tenant_id IS NULL;

  SELECT count(*) INTO graph_relationship_count
  FROM stackgraph."Relationship";

  SELECT count(*) INTO missing_entity_count
  FROM entity relational
  LEFT JOIN stackgraph."Entity" graph
    ON trim(both '"' from ag_catalog.agtype_access_operator(
         VARIADIC ARRAY[graph.properties, '"entity_id"'::ag_catalog.agtype]
       )::text) = relational.id::text
  WHERE relational.tenant_id IS NULL
    AND graph.id IS NULL;

  SELECT count(*) INTO missing_relationship_count
  FROM current_relationship relational
  JOIN fact_assertion fact ON fact.id = relational.fact_assertion_id
  LEFT JOIN stackgraph."Relationship" graph
    ON trim(both '"' from ag_catalog.agtype_access_operator(
         VARIADIC ARRAY[graph.properties, '"fact_id"'::ag_catalog.agtype]
       )::text) = relational.fact_assertion_id::text
  WHERE fact.tenant_id IS NULL
    AND graph.id IS NULL;

  SELECT count(*) INTO pending_projection_count
  FROM projection_outbox
  WHERE aggregate_type = 'FACT' AND processed_at IS NULL;

  IF graph_entity_count <> relational_entity_count THEN
    RAISE EXCEPTION 'entity parity failed: relational %, graph %', relational_entity_count, graph_entity_count;
  END IF;
  IF graph_relationship_count <> relational_relationship_count THEN
    RAISE EXCEPTION 'relationship parity failed: relational %, graph %', relational_relationship_count, graph_relationship_count;
  END IF;
  IF missing_entity_count <> 0 THEN
    RAISE EXCEPTION 'AGE is missing % relational entities', missing_entity_count;
  END IF;
  IF missing_relationship_count <> 0 THEN
    RAISE EXCEPTION 'AGE is missing % current relationships', missing_relationship_count;
  END IF;
  IF pending_projection_count <> 0 THEN
    RAISE EXCEPTION '% projection events remain pending', pending_projection_count;
  END IF;
END
$$;

SELECT
  (SELECT count(*) FROM stackgraph."Entity") AS graph_entities,
  (SELECT count(*) FROM stackgraph."Relationship") AS graph_relationships,
  (SELECT count(*) FROM projection_outbox WHERE processed_at IS NULL) AS pending_events;
