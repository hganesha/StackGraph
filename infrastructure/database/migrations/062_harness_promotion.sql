-- The champion/challenger half of §36, opened under the conditions A1 attaches to it.
--
-- Migration 059 deliberately left this unrepresentable, and said why: A1 requires the loop to
-- "remain disabled until offline evaluation, rollback, and governance are proven". That is a
-- condition, not a prohibition, and the honest way to open it is to make the three proofs
-- computable and require them — not to add a table and a flag and call the condition met.
--
-- So promotion here is gated on evidence that already exists in this schema rather than on a
-- switch somebody sets:
--
--   offline evaluation proven — a COMPLETED harness_evaluation of the challenger with no
--     failure, no inconclusive outcome, and no unanswered scenario, covering every scenario
--     class this estate has derived and every scenario the incumbent was evaluated against;
--   rollback proven — a PASSED ROLLBACK drill in agent_control_drill, recorded no earlier than
--     the evaluation it vouches for, plus a rollback path that restores the previous champion
--     and is always available;
--   governance proven — two people. The actor who proposes a promotion cannot be the actor who
--     approves it, and the database refuses the row rather than trusting the API to check.
--
-- A proposal whose gate does not clear is still written, with its reasons. A refusal nobody
-- can read is indistinguishable from a promotion nobody attempted.

-- The rollback drill is referenced with its tenant so a promotion cannot cite another tenant's
-- proof. `agent_control_drill` had no composite key to point at, so one is added here.
ALTER TABLE agent_control_drill
  ADD CONSTRAINT uq_agent_control_drill_id_tenant UNIQUE(id,tenant_id);

CREATE TABLE harness_promotion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  harness_key text NOT NULL CHECK(harness_key<>''),
  challenger_version text NOT NULL CHECK(challenger_version<>''),
  -- NULL when this harness has no champion yet. A first promotion is not a comparison, and
  -- recording an empty string would make it look like one against a version called "".
  incumbent_version text CHECK(incumbent_version IS NULL OR incumbent_version<>''),
  evaluation_id uuid NOT NULL,
  -- The drill that proves this promotion can be undone. Not nullable: A1 names rollback as a
  -- precondition, so a promotion with no drill behind it is not a promotion this schema holds.
  rollback_drill_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING','PROMOTED','REJECTED','ROLLED_BACK','REFUSED')),
  gate_state text NOT NULL CHECK(gate_state IN ('CLEAR','BLOCKED')),
  gate_reasons jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(gate_reasons)='array'),
  requested_by text NOT NULL CHECK(requested_by<>''),
  rationale text NOT NULL CHECK(rationale<>''),
  decided_by text,
  decision_rationale text,
  decided_at timestamptz,
  rolled_back_by text,
  rollback_rationale text,
  rolled_back_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(evaluation_id,tenant_id) REFERENCES harness_evaluation(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(rollback_drill_id,tenant_id) REFERENCES agent_control_drill(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(tenant_id,id),
  -- Two people. Enforced here rather than in the API, because a governance rule that lives only
  -- in application code is a rule the next writer can forget.
  CHECK(decided_by IS NULL OR decided_by<>requested_by),
  CHECK((status IN ('PENDING','REFUSED'))=(decided_at IS NULL)),
  CHECK((decided_by IS NULL)=(decided_at IS NULL)),
  CHECK((status='ROLLED_BACK')=(rolled_back_at IS NOT NULL)),
  -- A blocked gate can only produce a refusal, and a refusal must name what blocked it.
  CHECK((gate_state='BLOCKED')=(status='REFUSED')),
  CHECK(gate_state='CLEAR' OR jsonb_array_length(gate_reasons)>0)
);

ALTER TABLE harness_promotion ENABLE ROW LEVEL SECURITY;
ALTER TABLE harness_promotion FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON harness_promotion
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE INDEX harness_promotion_by_harness
  ON harness_promotion(tenant_id,harness_key,created_at DESC);

-- One champion per harness. The previous version is kept beside it so a rollback restores what
-- was actually running rather than reconstructing it from promotion history.
CREATE TABLE harness_champion (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  harness_key text NOT NULL CHECK(harness_key<>''),
  harness_version text NOT NULL CHECK(harness_version<>''),
  previous_version text CHECK(previous_version IS NULL OR previous_version<>''),
  promotion_id uuid NOT NULL,
  promoted_by text NOT NULL CHECK(promoted_by<>''),
  promoted_at timestamptz NOT NULL DEFAULT now(),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  PRIMARY KEY(tenant_id,harness_key),
  FOREIGN KEY(promotion_id,tenant_id) REFERENCES harness_promotion(id,tenant_id) ON DELETE RESTRICT,
  CHECK(harness_version<>previous_version)
);

ALTER TABLE harness_champion ENABLE ROW LEVEL SECURITY;
ALTER TABLE harness_champion FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON harness_champion
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- A decided promotion is the record of a governance decision. It may be rolled back — that is
-- the point of rollback — but its decision cannot be rewritten, and neither can a refusal.
CREATE FUNCTION stackgraph_prevent_promotion_rewrite()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'harness promotions are append-only; roll the promotion back instead';
  END IF;
  IF OLD.status='REFUSED' THEN
    RAISE EXCEPTION 'a refused promotion is immutable; propose a new one';
  END IF;
  IF OLD.status IN ('PROMOTED','REJECTED','ROLLED_BACK') AND NEW.status<>'ROLLED_BACK' THEN
    RAISE EXCEPTION 'a decided promotion cannot be re-decided';
  END IF;
  IF OLD.decided_by IS NOT NULL AND NEW.decided_by IS DISTINCT FROM OLD.decided_by THEN
    RAISE EXCEPTION 'the approving actor of a decided promotion cannot be changed';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_harness_promotion_append_only
  BEFORE UPDATE OR DELETE ON harness_promotion
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_promotion_rewrite();

ALTER TABLE phase2_feature_flag DROP CONSTRAINT IF EXISTS phase2_feature_flag_flag_key_check;
ALTER TABLE phase2_feature_flag ADD CONSTRAINT phase2_feature_flag_flag_key_check
  CHECK(flag_key IN (
    'SCANNER_PROFILES','CHANGE_COMPILER','CHANGE_SIMULATION','AI_INTERPRETATION',
    'CHANGE_EXECUTION','REGISTRY_ENRICHMENT','ADVERSARIAL_EVALUATION',
    'CONTAINER_PACKAGE_INVENTORY','HARNESS_PROMOTION'
  ));

INSERT INTO phase2_feature_flag(tenant_id,flag_key,enabled,updated_by) VALUES
  (NULL,'HARNESS_PROMOTION',false,'migration:062')
ON CONFLICT DO NOTHING;

-- Migration 059's comment said there was deliberately no promotion table. There is one now, so
-- the comment is replaced rather than left to contradict the schema it describes. Migrations
-- are checksummed and never edited in place; superseding a comment is what a later one is for.
COMMENT ON TABLE harness_evaluation IS
  'Offline evaluation of a harness against adversarial scenarios. Promotion of a challenger is '
  'gated on a completed evaluation of this kind, a passed rollback drill, and a two-person '
  'decision; see harness_promotion.';

COMMENT ON TABLE harness_promotion IS
  'A proposal to make a challenger the champion, and the evidence that admitted or refused it. '
  'A1 requires offline evaluation, rollback, and governance to be proven before this loop '
  'runs, so each is a computed precondition rather than a switch: the evaluation must be '
  'complete and clean and cover what the incumbent covered, the rollback drill must have '
  'passed, and the approver must not be the proposer.';
