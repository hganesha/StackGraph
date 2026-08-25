import type { ModernizationCandidate, RepositoryDetail } from "@stackgraph/shared";
import {
  presentRecommendationRationale,
  presentRecommendationTitle,
  presentValidationGap,
} from "@/lib/modernizationPresentation";

function section(heading: string, lines: string[]) {
  if (lines.length === 0) return "";
  return `## ${heading}\n\n${lines.map((line) => `- ${line}`).join("\n")}\n`;
}

function orderedSection(heading: string, steps: string[], emptyNote: string) {
  const body = steps.length > 0
    ? steps.map((step, index) => `${index + 1}. ${step}`).join("\n")
    : emptyNote;
  return `## ${heading}\n\n${body}\n`;
}

/**
 * Renders a modernization recommendation as a hand-off document — the artifact a
 * business user gives an engineer to implement, not a machine-readable export. Built
 * entirely from data already loaded on the recommendation focus page; no extra fetch.
 */
export function recommendationToMarkdown(
  candidate: ModernizationCandidate,
  repository: RepositoryDetail,
): string {
  const recommendation = candidate.recommendation;
  if (!recommendation) return "";

  const application = repository.applications[0];
  const confidencePct = Math.round(recommendation.confidence * 100);

  const parts = [
    `# ${presentRecommendationTitle(recommendation.title)}`,
    "",
    `**Action:** ${recommendation.action.toLowerCase()}  `,
    `**Estimated effort:** ${recommendation.estimated_effort.toLowerCase()}  `,
    `**Confidence:** ${confidencePct}%  `,
    `**Status:** ${recommendation.review_state.toLowerCase()}  `,
    `**Repository:** ${repository.repository.name} (\`${repository.repository.id}\`)  `,
    application ? `**Application:** ${application.name} (\`${application.id}\`)  ` : "**Application:** not linked  ",
    `**Affected:** ${recommendation.affected_files} files, ${recommendation.affected_call_sites} call sites`,
    "",
    "## Rationale",
    "",
    presentRecommendationRationale(recommendation.rationale),
    "",
    orderedSection(
      "Migration plan",
      recommendation.migration_plan,
      "No migration steps were recorded for this recommendation.",
    ),
    orderedSection(
      "Rollback plan",
      recommendation.rollback_plan,
      "No rollback steps were recorded for this recommendation.",
    ),
    section("What needs validation", candidate.validation_gaps.map(presentValidationGap)),
    section(
      "Affected modules",
      [...new Set(candidate.source_locations
        .map((location) => (typeof location.path === "string" ? location.path : null))
        .filter((path): path is string => Boolean(path)))],
    ),
    `_Exported from StackGraph · repository revision \`${candidate.source_revision.slice(0, 7)}\`_`,
  ];

  return parts.filter((part) => part !== "").join("\n");
}

export function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export function recommendationFilename(recommendationId: string): string {
  return `stackgraph-recommendation-${recommendationId.slice(0, 8)}.md`;
}
