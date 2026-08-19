"use client";

import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, sanitizeOrigin, formatDate } from "@stackgraph/shared";
import { Drawer, AssertionTag, ConfidenceChip, EvidenceRow, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./EvidenceDrawer.module.css";

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : undefined;
}

/** Globally mounted; opens on any surface's citation. Renders DECLARED→OBSERVED→INFERRED provenance. */
export function EvidenceDrawerHost() {
  const { factId, label, close } = useEvidenceStore();
  const { data, isLoading } = useQuery({
    queryKey: ["evidence", factId],
    queryFn: () => stackGraphClient.getFactEvidence(factId as string),
    enabled: !!factId,
  });

  const props = (data?.properties ?? {}) as Record<string, unknown>;
  const registry = (props.registry_resolution ?? {}) as Record<string, unknown>;
  const origin = str(registry.origin);

  return (
    <Drawer open={!!factId} onClose={close} title={label ?? "Evidence"}>
      {isLoading || !data ? (
        <div className={styles.loading}>
          <Skeleton height={20} width="60%" />
          <Skeleton height={14} width="90%" />
          <Skeleton height={14} width="80%" />
        </div>
      ) : (
        <div className={styles.body}>
          <div className={styles.meta}>
            <AssertionTag assertionClass={data.assertion_class} />
            <code className={`${styles.predicate} sg-mono`}>{data.predicate}</code>
            <ConfidenceChip label={confidenceLabel(data.confidence)} value={data.confidence} />
          </div>

          <dl className={styles.facts}>
            {str(props.resolved_version) ? (
              <>
                <dt>Resolved</dt>
                <dd className="sg-mono">{str(props.resolved_version)}</dd>
              </>
            ) : null}
            {str(props.scope) ? (
              <>
                <dt>Scope</dt>
                <dd className="sg-mono">{str(props.scope)}</dd>
              </>
            ) : null}
            {origin ? (
              <>
                <dt>Registry</dt>
                <dd className="sg-mono">{sanitizeOrigin(origin)}</dd>
              </>
            ) : null}
            <dt>Extractor</dt>
            <dd className="sg-mono">
              {data.extractor.key}@{data.extractor.version}
            </dd>
            <dt>Source rev</dt>
            <dd className="sg-mono">{data.source_revision.slice(0, 12)}</dd>
            <dt>Observed</dt>
            <dd>{formatDate(data.observed_at)}</dd>
          </dl>

          <h3 className={styles.h3}>Evidence</h3>
          <ul className={styles.rows}>
            {data.evidence.map((item, i) => {
              const e = item as Record<string, unknown>;
              const pointer = str(e.json_pointer);
              return (
                <EvidenceRow
                  key={i}
                  assertionClass={data.assertion_class}
                  source={str(e.path) ?? str(e.locator)}
                  description={[str(e.type), pointer].filter(Boolean).join(" · ")}
                />
              );
            })}
          </ul>
        </div>
      )}
    </Drawer>
  );
}
