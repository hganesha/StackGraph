"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  stackGraphClient,
  type ModernizationCandidate,
  type RepositoryDetail,
} from "@stackgraph/shared";
import { ConfidenceChip, Skeleton } from "@stackgraph/design-system";
import {
  presentRecommendationRationale,
  presentRecommendationTitle,
  presentValidationGap,
} from "@/lib/modernizationPresentation";
import styles from "./repository.module.css";

const INITIAL_MODULE_COUNT = 12;

interface SourceLocation {
  repositoryId: string;
  path: string;
  symbols: string[];
  ranges: string[];
  pointers: string[];
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function moduleLocations(candidate: ModernizationCandidate, defaultRepositoryId: string) {
  const grouped = new Map<string, SourceLocation>();

  for (const raw of candidate.source_locations) {
    const path = stringValue(raw.path);
    if (!path) continue;
    const repositoryId = stringValue(raw.repository_id) ?? defaultRepositoryId;
    const key = `${repositoryId}:${path}`;
    const location = grouped.get(key) ?? {
      repositoryId,
      path,
      symbols: [],
      ranges: [],
      pointers: [],
    };
    const symbol = stringValue(raw.symbol);
    const pointer = stringValue(raw.json_pointer);
    const lineStart = numberValue(raw.line_start);
    const lineEnd = numberValue(raw.line_end);
    if (symbol && !location.symbols.includes(symbol)) location.symbols.push(symbol);
    if (pointer && !location.pointers.includes(pointer)) location.pointers.push(pointer);
    if (lineStart !== undefined) {
      const range = lineEnd !== undefined && lineEnd !== lineStart
        ? `Lines ${lineStart}–${lineEnd}`
        : `Line ${lineStart}`;
      if (!location.ranges.includes(range)) location.ranges.push(range);
    }
    grouped.set(key, location);
  }

  return [...grouped.values()].sort((left, right) => {
    if (left.repositoryId === defaultRepositoryId && right.repositoryId !== defaultRepositoryId) return -1;
    if (right.repositoryId === defaultRepositoryId && left.repositoryId !== defaultRepositoryId) return 1;
    return left.path.localeCompare(right.path);
  });
}

function recommendationStatusLabel(state: string) {
  return state.toLowerCase().replaceAll("_", " ");
}

function FocusSkeleton() {
  return (
    <div className={styles.focusPage}>
      <Skeleton height={18} width="28%" />
      <Skeleton height={112} width="100%" />
      <Skeleton height={76} width="100%" />
      <div className={styles.focusSkeletonGrid}>
        <Skeleton height={320} />
        <Skeleton height={320} />
      </div>
    </div>
  );
}

export function RecommendationFocus({
  recommendationId,
  repository,
}: {
  recommendationId: string;
  repository: RepositoryDetail;
}) {
  const [showAllModules, setShowAllModules] = useState(false);
  const intelligence = useQuery({
    queryKey: ["repository", repository.repository.id, "modernization-intelligence"],
    queryFn: () => stackGraphClient.getRepositoryModernizationIntelligence(repository.repository.id, 100),
  });
  const candidate = intelligence.data?.candidates.find(
    (item) => item.recommendation?.id === recommendationId,
  );
  const modules = useMemo(
    () => candidate ? moduleLocations(candidate, repository.repository.id) : [],
    [candidate, repository.repository.id],
  );
  const relatedRepositoryIds = useMemo(
    () => [...new Set(modules.map((module) => module.repositoryId))]
      .filter((repositoryId) => repositoryId !== repository.repository.id),
    [modules, repository.repository.id],
  );
  const relatedRepositories = useQuery({
    queryKey: ["recommendation", recommendationId, "repositories", ...relatedRepositoryIds],
    queryFn: () => Promise.all(relatedRepositoryIds.map(async (repositoryId) => {
      try {
        return await stackGraphClient.getRepository(repositoryId);
      } catch {
        return null;
      }
    })),
    enabled: relatedRepositoryIds.length > 0,
  });

  if (intelligence.isLoading) return <FocusSkeleton />;

  if (!candidate?.recommendation) {
    return (
      <div className={styles.focusPage}>
        <nav className={styles.crumbs} aria-label="Breadcrumb">
          <Link href="/modernization">Modernization</Link>
          <span aria-hidden="true">›</span>
          <span>Recommendation</span>
        </nav>
        <section className={styles.focusUnavailable}>
          <span className={styles.eyebrow}>Recommendation unavailable</span>
          <h1>This recommendation is no longer part of the current repository analysis.</h1>
          <p>It may have been replaced by a newer scan or policy run.</p>
          <Link href="/modernization">Return to modernization</Link>
        </section>
      </div>
    );
  }

  const recommendation = candidate.recommendation;
  const detailsByRepository = new Map<string, RepositoryDetail>([
    [repository.repository.id, repository],
  ]);
  for (const detail of relatedRepositories.data ?? []) {
    if (detail) detailsByRepository.set(detail.repository.id, detail);
  }
  const visibleModules = showAllModules ? modules : modules.slice(0, INITIAL_MODULE_COUNT);
  const visibleRepositoryIds = [...new Set(visibleModules.map((module) => module.repositoryId))];
  const primaryApplication = repository.applications[0];

  return (
    <div className={styles.focusPage}>
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <Link href="/modernization">Modernization</Link>
        <span aria-hidden="true">›</span>
        {primaryApplication ? (
          <>
            <Link href={`/applications/${primaryApplication.id}`}>{primaryApplication.name}</Link>
            <span aria-hidden="true">›</span>
          </>
        ) : null}
        <span>Recommendation</span>
      </nav>

      <header className={styles.focusHead}>
        <div className={styles.focusTitle}>
          <div className={styles.focusMeta}>
            <span>{recommendation.action.toLowerCase()}</span>
            <span>{recommendation.estimated_effort.toLowerCase()} effort</span>
            <span>{recommendationStatusLabel(recommendation.review_state)}</span>
          </div>
          <h1>{presentRecommendationTitle(recommendation.title)}</h1>
          <p>{presentRecommendationRationale(recommendation.rationale)}</p>
        </div>
        <Link className={styles.backLink} href="/modernization">Back to modernization</Link>
      </header>

      <section className={styles.entityContext} aria-label="Application and repository context">
        <div>
          <span>Application</span>
          {primaryApplication ? (
            <Link href={`/applications/${primaryApplication.id}`}>{primaryApplication.name}</Link>
          ) : <strong>Not linked</strong>}
          <small>{repository.applications.length} connected application{repository.applications.length === 1 ? "" : "s"}</small>
        </div>
        <div>
          <span>Repository</span>
          <Link className="sg-mono" href={`/repositories/${repository.repository.id}`}>
            {repository.repository.name}
          </Link>
          <small>Open the full repository profile</small>
        </div>
        <div>
          <span>Exact modules</span>
          <strong className="sg-mono">{modules.length}</strong>
          <small>Across {relatedRepositoryIds.length + 1} repositor{relatedRepositoryIds.length === 0 ? "y" : "ies"}</small>
        </div>
      </section>

      <div className={styles.focusLayout}>
        <section className={styles.modulesPanel} aria-labelledby="affected-modules-heading">
          <div className={styles.focusSectionHead}>
            <div>
              <span className={styles.eyebrow}>Affected code</span>
              <h2 id="affected-modules-heading">Modules behind this recommendation</h2>
              <p>These are the files and symbols the analysis matched. Review them before changing shared behavior.</p>
            </div>
            <span>{modules.length}</span>
          </div>

          {modules.length === 0 ? (
            <p className={styles.empty}>No exact source locations were recorded for this recommendation.</p>
          ) : visibleRepositoryIds.map((repositoryId) => {
            const detail = detailsByRepository.get(repositoryId);
            const repositoryModules = visibleModules.filter((module) => module.repositoryId === repositoryId);
            const application = detail?.applications[0];
            return (
              <section key={repositoryId} className={styles.moduleGroup} aria-label={`${detail?.repository.name ?? "Related repository"} modules`}>
                <header className={styles.moduleGroupHead}>
                  <div>
                    <span>Repository</span>
                    <Link className="sg-mono" href={`/repositories/${repositoryId}`}>
                      {detail?.repository.name ?? "Related repository"}
                    </Link>
                  </div>
                  {application ? (
                    <div>
                      <span>Application</span>
                      <Link href={`/applications/${application.id}`}>{application.name}</Link>
                    </div>
                  ) : null}
                </header>
                <ul className={styles.moduleList}>
                  {repositoryModules.map((module) => (
                    <li key={`${module.repositoryId}:${module.path}`}>
                      <code className="sg-mono">{module.path}</code>
                      <div className={styles.moduleDetails}>
                        {module.symbols.length > 0 ? <strong className="sg-mono">{module.symbols.join(", ")}</strong> : null}
                        {module.ranges.map((range) => <span key={range}>{range}</span>)}
                        {module.pointers.map((pointer) => <span key={pointer} className="sg-mono">{pointer}</span>)}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}

          {modules.length > INITIAL_MODULE_COUNT ? (
            <button
              type="button"
              className={styles.showModules}
              onClick={() => setShowAllModules((current) => !current)}
            >
              {showAllModules ? "Show the first 12 modules" : `Show all ${modules.length} modules`}
            </button>
          ) : null}
        </section>

        <aside className={styles.focusSidebar} aria-label="Recommendation details">
          <section className={styles.sideSection}>
            <div className={styles.sideHeading}>
              <h2>Estimated impact</h2>
              <ConfidenceChip
                label={recommendation.confidence >= 0.85 ? "HIGH" : recommendation.confidence >= 0.7 ? "MEDIUM" : "LOW"}
                value={recommendation.confidence}
              />
            </div>
            <dl className={styles.impactFacts}>
              <div><dt>Affected files</dt><dd>{recommendation.affected_files}</dd></div>
              <div><dt>Call sites</dt><dd>{recommendation.affected_call_sites}</dd></div>
              <div><dt>Effort</dt><dd>{candidate.impact?.effort_points ?? "—"}<span> points</span></dd></div>
              <div><dt>Revision</dt><dd title={candidate.source_revision}>{candidate.source_revision.slice(0, 7)}</dd></div>
            </dl>
          </section>

          <section className={styles.sideSection}>
            <h2>What needs validation</h2>
            <ul className={styles.compactList}>
              {candidate.validation_gaps.slice(0, 4).map((gap) => (
                <li key={gap}>{presentValidationGap(gap)}</li>
              ))}
            </ul>
          </section>

          <section className={styles.sideSection}>
            <h2>Suggested next steps</h2>
            <ol className={styles.compactList}>
              {recommendation.migration_plan.slice(0, 3).map((step) => <li key={step}>{step}</li>)}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}
