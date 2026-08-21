export function presentRecommendationTitle(title: string) {
  const duplicateMatch = title.match(/^Review duplicated (.+?) implementations$/i);
  if (duplicateMatch) {
    const subject = duplicateMatch[1].trim();
    return subject.toLowerCase() === "implementation"
      ? "Review duplicate code"
      : `Review duplicate ${subject} code`;
  }

  return title
    .replace(/\bimplementation implementations\b/gi, "code")
    .replace(/\bduplicated\b/gi, "duplicate");
}

export function presentRecommendationSummary(summary?: string) {
  if (!summary) return summary;

  const duplicateMatch = summary.match(
    /^(.+?) · (\d+) code units share a structural fingerprint across (\d+) repositories?\.?/i,
  );
  if (duplicateMatch) {
    const [, repository, unitCount, repositoryCount] = duplicateMatch;
    const repositoryLabel = Number(repositoryCount) === 1 ? "repository" : "repositories";
    return `${repository} · ${unitCount} matching code units across ${repositoryCount} ${repositoryLabel}`;
  }

  return summary
    .replace(/Confirm behavioral equivalence.*$/i, "")
    .replace(/structural fingerprint/gi, "matching structure")
    .trim();
}

export function presentRecommendationRationale(rationale: string) {
  const duplicateMatch = rationale.match(
    /^(\d+) code units share a structural fingerprint across (\d+) repositories?\./i,
  );
  if (!duplicateMatch) return rationale.replace(/structural fingerprint/gi, "matching code pattern");

  const [, moduleCount, repositoryCount] = duplicateMatch;
  const moduleLabel = Number(moduleCount) === 1 ? "module" : "modules";
  const repositoryLabel = Number(repositoryCount) === 1 ? "repository" : "repositories";
  return `The same code pattern appears in ${moduleCount} ${moduleLabel} across ${repositoryCount} ${repositoryLabel}. Confirm they behave the same before consolidating them.`;
}

export function presentValidationGap(gap: string) {
  const missingTests = gap.match(/^(\d+) affected call sites? (?:has|have) no statically linked test file\.$/i);
  if (missingTests) {
    const count = Number(missingTests[1]);
    return `${count} affected call ${count === 1 ? "site has" : "sites have"} no linked test.`;
  }
  if (/^Matching structure does not prove matching behavior or intent\.$/i.test(gap)) {
    return "The matching code may still behave differently.";
  }
  return gap;
}
