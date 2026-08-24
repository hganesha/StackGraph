import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const billingApplication = "/applications/00000000-0000-4000-8000-000000000201";

// Graph intelligence opens two drawers over the page, and a hand-rolled modal is exactly
// where focus and aria-modal defects hide, so the drawers are checked open rather than
// only the page behind them.
async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(
    ({ impact }) => impact === "serious" || impact === "critical",
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test("application overview exposes snapshot intelligence and explainable similarity", async ({ page }) => {
  await page.goto(billingApplication);

  const panel = page.getByRole("region", { name: "Structurally critical" });
  await expect(panel.getByRole("heading", { name: "Structurally critical" })).toBeVisible();
  await expect(panel.getByText("Upstream impact", { exact: true })).toBeVisible();
  await expect(panel.getByText("Bridge / SPOF")).toBeVisible();

  await panel.getByRole("button", { name: "View blast radius" }).click();
  const blast = page.getByRole("dialog", { name: "Blast radius" });
  await expect(blast.getByText("Affected entities")).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
  await blast.getByRole("button", { name: "Close drawer" }).click();

  await panel.getByRole("button", { name: "Similar applications" }).click();
  const similarity = page.getByRole("dialog", { name: "Similar applications" });
  await expect(similarity.getByText("Ledger API", { exact: true })).toBeVisible();
  await expect(similarity.getByRole("heading", { name: "Why it matches" })).toBeVisible();
  await expect(similarity.getByRole("heading", { name: "What is different" })).toBeVisible();
  await expect(similarity.getByText("Billing and invoicing")).toBeVisible();
  await expect(similarity.getByText(/financial reconciliation/)).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("structural vocabulary is defined where it is used", async ({ page }, testInfo) => {
  await page.goto(billingApplication);

  const panel = page.getByRole("region", { name: "Structurally critical" });
  const term = panel.getByRole("button", { name: "Bridge / SPOF" });
  await expect(term).toBeVisible();

  // Closed by default, so a screen reader reading the metric does not hear the whole
  // definition spliced into it.
  await expect(term).toHaveAttribute("aria-expanded", "false");

  if (testInfo.project.name !== "mobile") {
    await term.focus();
    await expect(term).toHaveAttribute("aria-expanded", "true");
    await expect(panel.getByRole("tooltip")).toContainText("split the graph");
  }
});

test("blast-radius evidence opens on top of the drawer that raised it", async ({ page }) => {
  await page.goto(billingApplication);

  const panel = page.getByRole("region", { name: "Structurally critical" });
  await panel.getByRole("button", { name: "View blast radius" }).click();
  const blast = page.getByRole("dialog", { name: "Blast radius" });

  await blast.getByRole("button", { name: /^Evidence / }).first().click();
  await expect(page.getByRole("dialog", { name: /Blast-radius path fact/ })).toBeVisible();
});

test("scan health reports graph and semantic readiness", async ({ page }) => {
  await page.goto("/health");

  await expect(page.getByRole("heading", { name: "Graph intelligence" })).toBeVisible();
  await expect(page.getByText("Projection lag")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Semantic intelligence" })).toBeVisible();
  await expect(page.getByText("Active coverage")).toBeVisible();
  await expect(page.getByText("100%")).toBeVisible();
});

test("architecture risk findings open the impacted application", async ({ page }) => {
  await page.goto("/ask");

  const risk = page.getByRole("link", { name: /billing-svc/i });
  await expect(risk).toHaveAttribute("href", billingApplication);
  await expect(risk.getByText("Repository · impacts Billing API")).toBeVisible();

  await risk.click();
  await expect(page).toHaveURL(billingApplication);
  await expect(page.getByRole("heading", { name: "Billing API" })).toBeVisible();
});

test("a similarity candidate is decided in the queue, with a reason", async ({ page }) => {
  await page.goto("/reviews");

  const candidate = page.locator("li").filter({ hasText: "Billing API ↔ Ledger API" });
  await expect(candidate).toBeVisible();

  // The decision used to be impossible here: the row said "Open where this was found
  // to review it" and offered no link.
  await candidate.getByRole("button", { name: "Consider consolidating" }).click();

  // A reason is required, so the submit stays disabled until one is chosen.
  const submit = candidate.getByRole("button", { name: /^Record consider consolidating$/ });
  await expect(submit).toBeDisabled();

  await candidate.getByRole("radio", { name: "Their functions overlap enough to merge" }).check();
  await candidate.getByRole("textbox", { name: /future reader/ }).fill("Both settle the same ledger.");
  await expect(submit).toBeEnabled();

  await submit.click();
  await expect(candidate.getByText(/Recorded as consolidation candidate/)).toBeVisible();
});

test("queue findings decided elsewhere link to where they were found", async ({ page }) => {
  await page.goto("/reviews");

  const recommendation = page.locator("li").filter({ hasText: "Replace bespoke retry helper" });
  await expect(recommendation.getByRole("link", { name: /Open the repository/ })).toBeVisible();
});

test("an entity says which community it sits in, and what that means", async ({ page }) => {
  await page.goto(billingApplication);

  const panel = page.getByRole("region", { name: "Structurally critical" });
  // Asserted around the glossary term rather than through it: Term keeps its definition
  // in the same paragraph, so a match spanning the word itself also spans the tooltip.
  await expect(panel.getByText(/of 14 entities that depend on each other/)).toBeVisible();
  await expect(panel.getByText(/alongside Ledger API/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "community" })).toBeVisible();

  // A community is a shape in the graph, not a team — the panel has to say so, because
  // "community" reads as ownership to almost everyone.
  await expect(panel.getByText(/not by ownership/)).toBeVisible();
});

test("filtering by name also offers what reads like the term", async ({ page }) => {
  await page.goto("/estate");
  await expect(page.getByRole("heading", { name: "Estate" })).toBeVisible();

  await page.getByRole("searchbox", { name: "Filter by name" }).fill("invoice");

  const related = page.getByRole("region", { name: "Related by meaning" });
  // "Ledger API" contains none of the letters of "invoice" — a name filter alone would
  // never surface it, which is the whole reason this group exists.
  await expect(related.getByRole("link", { name: /Ledger API/ })).toBeVisible();
  await expect(related.getByText(/never proof of a relationship/)).toBeVisible();
  await expect(related.getByText(/no approximate index was used/)).toBeVisible();
});

test("a term nothing reads like says so, and leaves name filtering alone", async ({ page }) => {
  await page.goto("/estate");
  await page.getByRole("searchbox", { name: "Filter by name" }).fill("zzzz");

  const related = page.getByRole("region", { name: "Related by meaning" });
  await expect(related.getByText(/Nothing in the evaluated space reads like/)).toBeVisible();
});
