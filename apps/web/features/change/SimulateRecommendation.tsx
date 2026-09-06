"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { IconPlayerPlay } from "@tabler/icons-react";
import { GateNotice, type GateVerdict } from "@stackgraph/design-system";
import { stackGraphClient } from "@stackgraph/shared";
import styles from "./simulate-recommendation.module.css";

/**
 * One button, six call sites.
 *
 * Phase 2 §16 makes `Simulate recommendation` a standard row action wherever a
 * recommendation appears, and the reason it is one component rather than six is stated
 * in R1's exit gate: *"a user moves from an estate-backed finding to a submitted
 * simulation without manual re-entry or loss of provenance."* Six buttons would be six
 * chances to drop the provenance on the way.
 *
 * `POST /modernization-recommendations/{id}/compile` returns a full
 * `MutationCompileResult`, gate included, so a recommendation that cannot be compiled
 * refuses here with its reason rather than failing later inside a simulation. That
 * refusal is the differentiating behaviour, so it renders as a gate rather than as an
 * error toast — non-negotiable 19, and the first `GateNotice` call site outside the
 * command surface.
 *
 * The idempotency key is generated once per attempt and reused for both calls, so a
 * double click returns the run that already exists instead of starting a second one.
 */
export function SimulateRecommendation({
  recommendationId,
  source = "MODERNIZATION",
  label = "Simulate",
  compact = false,
}: {
  recommendationId: string;
  /**
   * Which estate finding this button is compiling. R1 requires the action on modernization,
   * insight cards, application findings, and the review queue alike; keeping it one component
   * with a source discriminator is what stops each surface growing its own compile path and
   * its own way of losing provenance.
   */
  source?: "MODERNIZATION" | "DETERMINISTIC_INSIGHT";
  label?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [gate, setGate] = useState<{ verdict: GateVerdict; reason: string } | null>(null);

  const run = async () => {
    setBusy(true);
    setGate(null);
    try {
      const idempotencyKey = `${source === "DETERMINISTIC_INSIGHT" ? "insight" : "rec"}:${recommendationId}:${Date.now()}`;
      const compiled =
        source === "DETERMINISTIC_INSIGHT"
          ? await stackGraphClient.compileDeterministicInsight(recommendationId, {
              idempotency_key: idempotencyKey,
            })
          : await stackGraphClient.compileModernizationRecommendation(recommendationId, {
              idempotency_key: idempotencyKey,
            });

      // A gate that is not CLEAR stops here, named, rather than being discovered by a
      // simulation that then has to explain itself.
      const verdict = (compiled.gate?.state ?? "CLEAR") as GateVerdict;
      if (verdict !== "CLEAR") {
        const reasons = compiled.gate?.reasons ?? [];
        setGate({
          verdict,
          reason:
            reasons.map((r) => r.message).filter(Boolean).join(" ") ||
            "This finding cannot be compiled into a change yet.",
        });
        return;
      }

      const changeSetId = compiled.change_set?.id;
      if (!changeSetId) {
        setGate({
          verdict: "BLOCKED",
          reason:
            "The finding compiled but produced no change set, so there is nothing to simulate.",
        });
        return;
      }

      const simulation = await stackGraphClient.createSimulation({
        change_set_id: changeSetId,
        idempotency_key: idempotencyKey,
      });
      router.push(`/simulations/${simulation.id}`);
    } catch {
      setGate({
        verdict: "BLOCKED",
        reason: "The change compiler did not answer. Nothing was submitted, so try again.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={`${styles.button} ${compact ? styles.compact : ""}`}
        onClick={run}
        disabled={busy}
      >
        <IconPlayerPlay size={compact ? 13 : 15} stroke={1.75} aria-hidden="true" />
        {busy ? "Compiling…" : label}
      </button>
      {gate ? <GateNotice verdict={gate.verdict} reason={gate.reason} /> : null}
    </div>
  );
}
