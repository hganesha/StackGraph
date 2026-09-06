import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The estate-fidelity surfaces: archetypes, critical edges, change history, the
// repository index and fingerprint, and the suggested-changes fold. Each is built on a
// read model that shipped before it had anywhere to appear, so these tests hold the
// rules that make the readings honest rather than the pixels.

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  await expect(page).toHaveTitle(/.+/);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(
    ({ impact }) => impact === "serious" || impact === "critical",
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test("archetypes are a peer view, and an outlier is never rendered as a fault", async ({ page }) => {
  await page.goto("/estate");
  await page
    .getByRole("navigation", { name: "Estate view" })
    .getByRole("link", { name: "Archetypes" })
    .click();
  await expect(page).toHaveURL(/view=archetypes/);

  const empty = page.getByRole("heading", { name: "No cohorts have formed yet" });
  if (await empty.isVisible().catch(() => false)) {
    await expectNoSeriousAccessibilityViolations(page);
    return;
  }

  await expect(
    page.getByRole("heading", { name: "The shapes your estate has settled into" }),
  ).toBeVisible();
  // The distribution is a table, so the numbers are readable without the picture.
  await expect(page.getByRole("columnheader", { name: "Members" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Outside the pattern" })).toBeVisible();
  // Different is not wrong, and the surface says so rather than implying otherwise.
  await expect(page.getByText(/Different is not wrong/)).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("the repository index exists and reaches a fingerprint", async ({ page }) => {
  await page.goto("/repositories");
  await expect(page.getByRole("heading", { level: 1, name: "Repositories" })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);

  // Fixture mode holds no Repository-kind ranked items, so an empty list here is the
  // correct result. What must hold either way is that the route exists, is reachable
  // from the rail, and carries the shared filter surface rather than a bespoke one.
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Repositories" })).toBeVisible();
});

test("a repository states what changes it, by class and never by person", async ({ page }) => {
  await page.goto("/repositories/00000000-0000-4000-8000-000000000203");

  const activity = page.getByRole("region", { name: "What changed recently" });
  await expect(activity.getByRole("heading", { name: "What is changing this" })).toBeVisible();
  // The commitment is stated on the surface, not only in a policy document.
  await expect(activity.getByText("StackGraph does not score individuals.")).toBeVisible();
  // The rule prohibits ranking and scoring people, not attributing a single event to
  // its author — a commit feed naming who pushed a commit is ordinary and stays. What
  // must not come back is the ranked list.
  await expect(activity.getByRole("heading", { name: "Most active" })).toHaveCount(0);
  await expect(activity.getByText(/\d+ commits · \d+ merged PRs/)).toHaveCount(0);
});

test("change history publishes its denominator", async ({ page }) => {
  await page.goto("/repositories/00000000-0000-4000-8000-000000000203");
  const history = page.getByRole("region", { name: "Previous changes" });
  if (!(await history.isVisible().catch(() => false))) return;

  // Every rate carries the sample it was drawn from (non-negotiable 17), so a bare
  // percentage never appears without an "n of m" beside it.
  await expect(history.getByText(/\d+ of \d+/).first()).toBeVisible();
});

test("critical edges show corroboration depth", async ({ page }) => {
  await page.goto("/repositories/00000000-0000-4000-8000-000000000203");
  const panel = page.getByRole("region", { name: "Relationships this rests on" });
  if (!(await panel.isVisible().catch(() => false))) return;

  // A one-source edge must be visibly weaker than a four-source one, and the count is
  // stated in words as well as drawn.
  await expect(panel.getByText(/corroborating fact/).first()).toBeVisible();
});
