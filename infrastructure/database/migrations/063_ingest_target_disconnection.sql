-- Record that somebody stopped scanning a repository, rather than only that it is not running.
--
-- Removing a repository from scanning deletes its connector and disables its ingest target. The
-- target survives, which is right — it holds the repository's promoted identity, its cursors and
-- its run history — but `enabled=false` cannot say whether scanning stopped because a person
-- stopped it, because a scheduler paused it, or because it was never started. Those are three
-- different situations and only one of them is a decision somebody made.
--
-- Re-adding the repository then has to find that row again. It is found by identity, not by the
-- key it was created with: a scanned repository's target_key has been promoted from
-- `github:repo-name:<owner>/<name>` to the canonical `github:repo:<id>`, so an upsert keyed on
-- the pending name inserts a second target for one repository — and the next scan promotes it
-- onto the key the first one already holds, which is the unique violation this fixes.

ALTER TABLE ingest_target
  ADD COLUMN IF NOT EXISTS disabled_at timestamptz,
  ADD COLUMN IF NOT EXISTS disabled_by text;

ALTER TABLE ingest_target DROP CONSTRAINT IF EXISTS ingest_target_disabled_recorded;
ALTER TABLE ingest_target ADD CONSTRAINT ingest_target_disabled_recorded
  -- Together or not at all: a timestamp with nobody attached is not a record of a decision.
  CHECK((disabled_at IS NULL)=(disabled_by IS NULL));

-- Targets already disabled when this migration runs were stopped by somebody the database never
-- recorded. They are marked as such rather than backfilled with a plausible actor, because a
-- guessed name in an audit trail is worse than an admitted gap.
UPDATE ingest_target
SET disabled_at=updated_at, disabled_by='unknown:before-migration-063'
WHERE NOT enabled AND disabled_at IS NULL;

COMMENT ON COLUMN ingest_target.disabled_at IS
  'When scanning was stopped for this target. NULL while it is enabled, and cleared when a '
  'target is resumed, so the pair always describes the current stop rather than accumulating '
  'a history the run records already hold.';

COMMENT ON COLUMN ingest_target.disabled_by IS
  'Who stopped scanning. Set together with disabled_at and never inferred.';
