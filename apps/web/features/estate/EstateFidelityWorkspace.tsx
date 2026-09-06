"use client";

import { useState, type FormEvent } from "react";
import {
  IconAlertTriangle,
  IconBrain,
  IconCheck,
  IconDatabaseShare,
  IconGitBranch,
  IconNotes,
} from "@tabler/icons-react";
import { ConfidenceChip, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import { useCan } from "@/lib/session";
import { useEstateSummary } from "@/lib/queries";
import {
  useAISupplyChain,
  useAssumptions,
  useContradictions,
  useCreateAssumption,
  useEstateLineage,
  useResolveContradiction,
} from "@/lib/estateFidelityQueries";
import styles from "./estate-fidelity.module.css";

function LoadingPanel() {
  return <div className={styles.loading}><Skeleton height={18} width="35%" /><Skeleton height={76} /></div>;
}

function Limitation({ message }: { message: string }) {
  return <p className={styles.limitation}><IconAlertTriangle size={16} aria-hidden="true" />{message}</p>;
}

export function EstateFidelityWorkspace() {
  const canReview = useCan("review");
  const estate = useEstateSummary();
  const lineage = useEstateLineage();
  const ai = useAISupplyChain();
  const assumptions = useAssumptions();
  const contradictions = useContradictions();
  const createAssumption = useCreateAssumption();
  const resolveContradiction = useResolveContradiction();
  const [subjectId, setSubjectId] = useState("");
  const [dimension, setDimension] = useState("");
  const [statement, setStatement] = useState("");
  const [authority, setAuthority] = useState("");
  const [resolution, setResolution] = useState<Record<string, string>>({});

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!subjectId || !dimension.trim() || !statement.trim() || !authority.trim()) return;
    await createAssumption.mutateAsync({
      subject_entity_id: subjectId,
      dimension: dimension.trim(),
      statement: statement.trim(),
      authority: authority.trim(),
      confidence: 1,
      last_verified_at: new Date().toISOString(),
      dependent_entity_ids: [],
      claims: [],
    });
    setDimension("");
    setStatement("");
    setAuthority("");
  };

  return (
    <div className={styles.workspace}>
      <section className={styles.intro}>
        <span>Governed estate evidence</span>
        <h2>Fidelity, lineage, and disagreement</h2>
        <p>Direct facts stay separate from assumptions. Missing integrations remain visible as limitations instead of inferred coverage.</p>
      </section>

      <div className={styles.grid}>
        <section className={styles.panel} aria-labelledby="lineage-heading">
          <header><IconGitBranch size={18} aria-hidden="true" /><div><h3 id="lineage-heading">Data lineage</h3><p>Normalized upstream-to-downstream evidence.</p></div></header>
          {lineage.isLoading ? <LoadingPanel /> : lineage.isError ? <Limitation message="Lineage could not be loaded." /> : lineage.data?.edges.length ? (
            <ol className={styles.rows}>
              {lineage.data.edges.map((edge) => <li key={edge.id}>
                <span><small>{edge.upstream.kind}</small><strong>{edge.upstream.name}</strong></span>
                <b aria-label="flows to">→</b>
                <span><small>{edge.downstream.kind}</small><strong>{edge.downstream.name}</strong></span>
                <ConfidenceChip label={confidenceLabel(edge.confidence)} value={edge.confidence} />
              </li>)}
            </ol>
          ) : <Limitation message={lineage.data?.limitations?.[0]?.message ?? "No normalized lineage evidence has been collected."} />}
        </section>

        <section className={styles.panel} aria-labelledby="ai-chain-heading">
          <header><IconBrain size={18} aria-hidden="true" /><div><h3 id="ai-chain-heading">AI supply chain</h3><p>Application → model, context, tool, data, and capability.</p></div></header>
          {ai.isLoading ? <LoadingPanel /> : ai.isError ? <Limitation message="AI supply-chain data could not be loaded." /> : ai.data?.links?.length ? (
            <>
              <div className={styles.coverage}><strong>{Math.round((ai.data.coverage_ratio ?? 0) * 100)}%</strong><span>type coverage · {ai.data.status.toLowerCase()}</span></div>
              <ol className={styles.chain}>
                {(ai.data.links ?? []).map((link, index) => <li key={`${link.subject.id}:${link.predicate}:${link.object.id}:${index}`}>
                  <strong>{link.subject.name}</strong><span>{link.predicate.replaceAll("_", " ").toLowerCase()}</span><strong>{link.object.name}</strong>
                </li>)}
              </ol>
            </>
          ) : <Limitation message={ai.data?.limitations?.[0]?.message ?? "AI supply-chain collection has not run for this estate."} />}
        </section>
      </div>

      <section className={styles.panel} aria-labelledby="contradictions-heading">
        <header><IconDatabaseShare size={18} aria-hidden="true" /><div><h3 id="contradictions-heading">Contradiction ledger</h3><p>Conflicting claims remain blocking until a reviewer records a reasoned decision.</p></div></header>
        {contradictions.isLoading ? <LoadingPanel /> : contradictions.isError ? <Limitation message="Contradictions could not be loaded." /> : contradictions.data?.contradictions.length ? (
          <ol className={styles.contradictions}>
            {contradictions.data.contradictions.map((item) => <li key={item.id}>
              <div className={styles.contradictionHead}><div><small>{item.predicate}</small><strong>{item.subject.name}</strong></div><span>{item.affected_entity_count} dependents</span></div>
              <ul>{item.claims.map((claim) => <li key={`${item.id}:${claim.claim_key}`}><b>{claim.display_value}</b><span>{claim.source_key} · {claim.assertion_class.toLowerCase()}</span></li>)}</ul>
              {canReview ? <form className={styles.resolve} onSubmit={async (event) => {
                event.preventDefault();
                const rationale = resolution[item.id]?.trim();
                if (!rationale) return;
                await resolveContradiction.mutateAsync({ id: item.id, body: { status: "RESOLVED", rationale, expected_version: item.version ?? 1 } });
              }}>
                <label><span>Resolution rationale</span><input value={resolution[item.id] ?? ""} onChange={(event) => setResolution((value) => ({ ...value, [item.id]: event.target.value }))} required /></label>
                <button type="submit" disabled={resolveContradiction.isPending}><IconCheck size={15} aria-hidden="true" />Resolve</button>
              </form> : null}
            </li>)}
          </ol>
        ) : <p className={styles.empty}>No open contradictions are recorded.</p>}
      </section>

      <section className={styles.panel} aria-labelledby="assumptions-heading">
        <header><IconNotes size={18} aria-hidden="true" /><div><h3 id="assumptions-heading">Assumption registry</h3><p>Named, versioned claims with an authority and last-verification date.</p></div></header>
        {assumptions.isLoading ? <LoadingPanel /> : assumptions.isError ? <Limitation message="Assumptions could not be loaded." /> : assumptions.data?.assumptions.length ? (
          <ol className={styles.assumptions}>{assumptions.data.assumptions.map((item) => <li key={item.id}>
            <div><small>{item.dimension} · v{item.version}</small><strong>{item.statement}</strong><span>{item.subject.name} · {item.authority}</span></div>
            <ConfidenceChip label={confidenceLabel(item.confidence)} value={item.confidence} />
          </li>)}</ol>
        ) : <p className={styles.empty}>No governed assumptions are recorded yet.</p>}

        {canReview ? <form className={styles.create} onSubmit={create}>
          <h4>Record an assumption</h4>
          <label><span>Subject</span><select value={subjectId} onChange={(event) => setSubjectId(event.target.value)} required><option value="">Choose an estate entity</option>{estate.data?.ranked_items.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.kind}</option>)}</select></label>
          <label><span>Dimension</span><input value={dimension} onChange={(event) => setDimension(event.target.value)} placeholder="runtime support" required /></label>
          <label className={styles.wide}><span>Statement</span><textarea value={statement} onChange={(event) => setStatement(event.target.value)} placeholder="State exactly what is being assumed." required /></label>
          <label><span>Authority</span><input value={authority} onChange={(event) => setAuthority(event.target.value)} placeholder="Architecture review board" required /></label>
          <button type="submit" disabled={createAssumption.isPending}>{createAssumption.isPending ? "Recording…" : "Record assumption"}</button>
          {createAssumption.isError ? <p role="alert">{createAssumption.error.message}</p> : null}
        </form> : null}
      </section>
    </div>
  );
}
