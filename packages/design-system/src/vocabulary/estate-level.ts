/**
 * How the product speaks about a component.
 *
 * `ChangeScope.kind` is `ESTATE | REPOSITORY | COMPONENT`, so a user meets a component
 * in the change compiler's scope picker before any surface exists to explain what one
 * is. Two lanes render components — the command surface and the estate surfaces — and
 * if each decides independently what a component looks like, the product ships two
 * vocabularies for one object.
 *
 * This module is that decision, made once. Both lanes import it; neither re-derives it.
 *
 * The rule underneath it is the one `vocabulary.ts` already states for domains:
 * distinguish by label, icon, and position, never by a new hue. Entity level is an open
 * axis in practice — a component is a level, not a kind, and kinds keep arriving — so it
 * cannot have a colour.
 */
export type EstateLevel = "ESTATE" | "REPOSITORY" | "COMPONENT";

export const ESTATE_LEVEL_LABEL: Record<EstateLevel, string> = {
  ESTATE: "Whole estate",
  REPOSITORY: "Repository",
  COMPONENT: "Component",
};

/**
 * What choosing this level actually promises, in the scope picker and anywhere else a
 * reader is asked to pick one. These are three different blast radii and the difference
 * is the entire reason `Component` was introduced.
 */
export const ESTATE_LEVEL_DESCRIPTION: Record<EstateLevel, string> = {
  ESTATE: "Everywhere this appears, across every repository StackGraph has scanned.",
  REPOSITORY: "Everything in the repository, including components the change does not touch.",
  COMPONENT: "Only this independently deployable part of the repository.",
};

/**
 * The noun each level counts, singular and plural.
 *
 * Non-negotiable 14: a repository count is not a component count. `affected_count` means
 * three different things depending on `kind`, so no surface may render it as a bare
 * number with an assumed noun.
 */
export const ESTATE_LEVEL_UNIT: Record<EstateLevel, { one: string; many: string }> = {
  ESTATE: { one: "entity", many: "entities" },
  REPOSITORY: { one: "repository", many: "repositories" },
  COMPONENT: { one: "component", many: "components" },
};

/** `3 components` / `1 repository`. Never a bare count. */
export function formatScopeCount(level: EstateLevel, count: number, locale?: string): string {
  const unit = ESTATE_LEVEL_UNIT[level];
  return `${count.toLocaleString(locale)} ${count === 1 ? unit.one : unit.many}`;
}

/**
 * `n components in m repositories` — the pair that stops a component-derived figure
 * overstating impact.
 *
 * A repository count that hides an unaffected component is the precise failure
 * `Component` exists to fix, so wherever the scope is component-derived, both numbers
 * are stated. Where only one is known, the other is omitted rather than guessed.
 */
export function formatComponentImpact(
  components: number,
  repositories: number | null | undefined,
  locale?: string,
): string {
  const left = formatScopeCount("COMPONENT", components, locale);
  if (repositories == null) return left;
  return `${left} in ${formatScopeCount("REPOSITORY", repositories, locale)}`;
}

/**
 * How a component is named on screen.
 *
 * A component's identity is its path within its repository, so the path is the name and
 * the repository is the context — `apps/payment-api`, qualified by `acme/platform` where
 * two repositories could both hold an `apps/payment-api`. The path is a scanned fact and
 * takes mono; the repository name is context and takes the surrounding type.
 *
 * Returned as parts rather than a string so a caller can render the two halves with the
 * right typeface. A caller that only needs text joins them with `·`.
 */
export interface ComponentLabelParts {
  /** The path within the repository. Mono — a scanner read this. */
  path: string;
  /** The owning repository, when the surface does not already establish it. */
  repository?: string;
}

export function componentLabelParts(
  componentPath: string,
  repositoryName?: string,
  options?: { repositoryIsImplied?: boolean },
): ComponentLabelParts {
  const path = componentPath.replace(/^\.?\//, "").trim() || componentPath;
  return options?.repositoryIsImplied || !repositoryName
    ? { path }
    : { path, repository: repositoryName };
}

/** Flat text form, for accessible names, titles, and anywhere markup is unavailable. */
export function componentLabelText(parts: ComponentLabelParts): string {
  return parts.repository ? `${parts.path} · ${parts.repository}` : parts.path;
}
