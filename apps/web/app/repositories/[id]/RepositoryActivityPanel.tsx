"use client";

import {
  IconExternalLink,
  IconGitCommit,
  IconGitPullRequest,
  IconUsers,
} from "@tabler/icons-react";
import {
  formatDate,
  formatRelative,
  type RepositoryActivity,
  type RepositoryActivityCoverageStatus,
  type RepositoryActivityEvent,
  type RepositoryActivityWindow,
} from "@stackgraph/shared";
import { Skeleton } from "@stackgraph/design-system";
import styles from "./RepositoryActivityPanel.module.css";

const WINDOWS: Array<{ value: RepositoryActivityWindow; label: string }> = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
];

function statusLabel(status: RepositoryActivityCoverageStatus) {
  if (status === "PERMISSION_REQUIRED") return "Permission required";
  if (status === "NOT_COLLECTED") return "Not collected";
  if (status === "ERROR") return "Unavailable";
  if (status === "PARTIAL") return "Partial";
  return null;
}

function metricValue(value: number | null | undefined, status: RepositoryActivityCoverageStatus) {
  if (status === "PARTIAL" && value != null) return `${value}+`;
  const unavailable = statusLabel(status);
  return unavailable ?? String(value ?? 0);
}

function eventLabel(event: RepositoryActivityEvent) {
  if (event.event_type === "COMMIT") return "Commit";
  if (event.event_type === "PULL_REQUEST_MERGED") return "PR merged";
  return "PR opened";
}

function EventIcon({ event }: { event: RepositoryActivityEvent }) {
  return event.event_type === "COMMIT"
    ? <IconGitCommit aria-hidden="true" size={18} stroke={1.7} />
    : <IconGitPullRequest aria-hidden="true" size={18} stroke={1.7} />;
}

export function RepositoryActivityPanel({
  data,
  isLoading,
  isError,
  window,
  onWindowChange,
}: {
  data?: RepositoryActivity;
  isLoading: boolean;
  isError: boolean;
  window: RepositoryActivityWindow;
  onWindowChange: (value: RepositoryActivityWindow) => void;
}) {
  return (
    <section className={styles.panel} aria-labelledby="repository-activity-heading">
      <header className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>Development activity</span>
          <h2 id="repository-activity-heading">What changed recently</h2>
          <p>Default-branch commits and pull-request activity observed from GitHub.</p>
        </div>
        <div className={styles.windows} role="group" aria-label="Activity window">
          {WINDOWS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={window === option.value}
              onClick={() => onWindowChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading ? (
        <div className={styles.loading}>
          <Skeleton height={92} />
          <Skeleton height={220} />
        </div>
      ) : isError ? (
        <p className={styles.error} role="alert">
          Repository activity could not be loaded. The repository profile remains available below.
        </p>
      ) : data ? (
        <>
          <dl className={styles.metrics}>
            <div>
              <dt><IconGitCommit aria-hidden="true" size={16} /> Commits</dt>
              <dd>{metricValue(data.summary.commits, data.coverage.commits)}</dd>
            </div>
            <div>
              <dt><IconGitPullRequest aria-hidden="true" size={16} /> PRs merged</dt>
              <dd>{metricValue(data.summary.pull_requests_merged, data.coverage.pull_requests)}</dd>
            </div>
            <div>
              <dt><IconUsers aria-hidden="true" size={16} /> Contributors</dt>
              <dd>{metricValue(data.summary.contributors, data.coverage.contributors)}</dd>
            </div>
            <div>
              <dt>Last activity</dt>
              <dd>
                {data.summary.last_change_at
                  ? formatRelative(data.summary.last_change_at)
                  : data.coverage.commits === "AVAILABLE" ? "No changes" : "Not collected"}
              </dd>
            </div>
          </dl>

          <div className={styles.body}>
            <div className={styles.timeline}>
              <div className={styles.subhead}>
                <h3>Recent changes</h3>
                <span>{data.events.length} shown</span>
              </div>
              {data.events.length ? (
                <ol className={styles.events}>
                  {data.events.map((event) => (
                    <li key={event.id}>
                      <span className={styles.eventIcon}><EventIcon event={event} /></span>
                      <div className={styles.eventContent}>
                        <div className={styles.eventMeta}>
                          <span>{eventLabel(event)}</span>
                          <time dateTime={event.occurred_at}>{formatDate(event.occurred_at)}</time>
                        </div>
                        {event.source_url ? (
                          <a href={event.source_url} target="_blank" rel="noreferrer">
                            {event.title}
                            <IconExternalLink aria-hidden="true" size={14} />
                          </a>
                        ) : <strong>{event.title}</strong>}
                        <small>
                          {event.actor ? `@${event.actor.login}` : "Unlinked author"}
                          {event.pull_request_number ? ` · #${event.pull_request_number}` : null}
                          {event.revision ? ` · ${event.revision.slice(0, 8)}` : null}
                        </small>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className={styles.empty}>
                  {data.coverage.commits === "AVAILABLE"
                    ? `No development activity was observed in this ${window.replace("d", "-day")} window.`
                    : "Development activity has not been collected for this repository yet."}
                </p>
              )}
            </div>

            <aside className={styles.contributors} aria-labelledby="repository-contributors-heading">
              <div className={styles.subhead}>
                <h3 id="repository-contributors-heading">Most active</h3>
                <span>{window.replace("d", " days")}</span>
              </div>
              {data.top_contributors.length ? (
                <ol>
                  {data.top_contributors.map((contributor) => (
                    <li key={contributor.actor.actor_key}>
                      <span className={styles.avatar} aria-hidden="true">
                        {contributor.actor.login.slice(0, 2).toUpperCase()}
                      </span>
                      <div>
                        <strong>@{contributor.actor.login}</strong>
                        <small>
                          {contributor.commits} commits · {contributor.pull_requests_merged} merged PRs
                        </small>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className={styles.empty}>No linked contributors are available for this window.</p>
              )}
            </aside>
          </div>

          {data.limitations.length ? (
            <details className={styles.limitations}>
              <summary>Activity coverage notes</summary>
              <ul>{data.limitations.map((value) => <li key={value}>{value}</li>)}</ul>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
