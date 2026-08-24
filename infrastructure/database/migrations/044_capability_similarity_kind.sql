ALTER TABLE application_similarity_candidate
  DROP CONSTRAINT application_similarity_candidate_entity_kind_check;
ALTER TABLE application_similarity_candidate
  ADD CONSTRAINT application_similarity_candidate_entity_kind_check CHECK(entity_kind IN (
    'Application','Technology','Capability','BusinessCapability'
  ));
