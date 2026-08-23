import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Fixture-mode governance state lives in a module-level store, so it resets on every
// full page load. Each test therefore drives the whole flow with client-side
// navigation, exactly as a real user would.

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

/**
 * Client-side navigation, because fixture-mode governance state resets on a full load.
 * On mobile the rail is an off-canvas drawer, so it has to be opened first — which is
 * also worth exercising: governance has to be reachable on a small screen, not just
 * survive being rendered there.
 */
async function railLink(page: Page, name: string, isMobile: boolean) {
  if (isMobile) await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name, exact: true }).click();
}

async function openArchitectureProfiles(page: Page) {
  await page.goto("/admin");
  await page.getByRole("tab", { name: /Policies & rules/ }).click();
  await page.getByRole("tab", { name: /Architecture profile/ }).click();
  await expect(page.getByRole("heading", { name: "Revisions" })).toBeVisible();
}

/** Creates a draft revision and lands on the canvas governing it. */
async function startGoverning(page: Page, isMobile: boolean) {
  await openArchitectureProfiles(page);
  await page.getByRole("button", { name: /New draft from active|Create first draft/ }).click();
  await expect(page.getByRole("row", { name: /draft/ })).toBeVisible();

  await railLink(page, "Architecture", isMobile);
  await expect(page.getByRole("heading", { level: 1, name: "Architecture" })).toBeVisible();
  await page.getByRole("radio", { name: "Target", exact: true }).click();
  await page.getByRole("checkbox", { name: /Govern draft/ }).check();
  await expect(page.getByText(/Editing draft v/)).toBeVisible();
}

test.describe("architecture profile lifecycle", () => {
  test("revisions, drafts, and publishing are legible in Admin", async ({ page }) => {
    await openArchitectureProfiles(page);

    // The revision in force is stated, because every projection resolves against it.
    await expect(page.getByRole("row", { name: /active/ })).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page);

    await page.getByRole("button", { name: /New draft from active/ }).click();

    // A draft is a new revision: the active one stays active until the draft is published.
    await expect(page.getByRole("row", { name: /v3.*active/ })).toBeVisible();
    await expect(page.getByRole("row", { name: /v4.*draft/ })).toBeVisible();

    // Inspecting the draft: this session created it, so its policies are known and shown.
    await page.getByRole("button", { name: /Inspect revision 4/ }).click();
    await expect(page.getByText(/with a decision recorded/)).toBeVisible();

    // Publishing changes what every team may ship, so it is never a single click.
    await page.getByRole("button", { name: /Publish this revision/ }).click();
    // Scoped: Next mounts its own route-announcer with role="alert".
    await expect(
      page.getByRole("alert").filter({ hasText: "applies this standard everywhere" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Publish revision", exact: true }).click();

    // Exactly one revision is ever in force. Publishing is itself a versioned write,
    // so the published revision carries the next version number.
    await expect(page.getByRole("row", { name: /v5.*active/ })).toBeVisible();
    await expect(page.getByRole("row", { name: /v3.*archived/ })).toBeVisible();
  });

  test("governing is refused, with a reason, when no draft is open", async ({ page }) => {
    await page.goto("/architecture");
    await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByRole("checkbox", { name: /Govern/ });
    await expect(toggle).toBeDisabled();
    // Editing the live standard in place would skip the publish step entirely.
    await expect(page.getByText(/No draft open/)).toBeVisible();
    await expect(page.getByRole("link", { name: /start one in Admin/ })).toBeVisible();
  });
});

test.describe("governing a draft", () => {
  test("an expectation change is written to the draft and states it is not yet in force", async ({ page }, testInfo) => {
    await startGoverning(page, testInfo.project.name === "mobile");

    // The target view resolves the revision in force; the API publishes no way to
    // preview a draft, and the banner says so rather than implying otherwise.
    await expect(page.getByText(/until you publish the draft/)).toBeVisible();

    const cell = page.locator('[data-cell-key="cell.data.database"]');
    await cell.getByRole("heading").click();
    const panel = page.locator('aside[aria-label$="detail"]');

    await panel.getByRole("button", { name: "Change what's expected" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Applicability").selectOption("OPTIONAL");
    await dialog
      .getByLabel(/Rationale/)
      .fill("The analytics product line ships without a relational store.");
    await dialog.getByRole("button", { name: "Record decision" }).click();

    // The write succeeded: the dialog closes rather than reporting a conflict.
    await expect(dialog).toBeHidden();
  });

  test("a decision that narrows what teams may ship requires a rationale", async ({ page }, testInfo) => {
    await startGoverning(page, testInfo.project.name === "mobile");

    await page.locator('[data-cell-key="cell.data.database"]').getByRole("heading").click();
    const panel = page.locator('aside[aria-label$="detail"]');
    await panel.getByRole("combobox").first().selectOption("PROHIBITED");

    const dialog = page.getByRole("dialog");
    const confirm = dialog.getByRole("button", { name: "Record decision" });
    await expect(confirm).toBeDisabled();
    await expect(dialog).toContainText("needs a reason on the record");

    await dialog.getByLabel(/Rationale/).fill("Superseded by the managed platform service.");
    await expect(confirm).toBeEnabled();
  });

  test("a migrated policy moves onto a cell with a stated decision and a name", async ({ page }, testInfo) => {
    await startGoverning(page, testInfo.project.name === "mobile");

    await page.getByRole("button", { name: /Not placed on the canvas/ }).click();
    await page.getByRole("tab", { name: /Unresolved policies/ }).click();

    await page.getByRole("button", { name: /Assign a cell/ }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Style Dictionary");
    // Migration never infers a decision: §7.3 forbids inventing REQUIRED or PREFERRED,
    // so the reviewer states it and it is recorded with their rationale.
    await dialog.getByLabel(/Decision for/).selectOption("PREFERRED");
    await dialog.getByLabel("Destination cell").selectOption({ label: "Design & accessibility" });
    await dialog.getByLabel(/Rationale/).fill("Design tokens belong with the design concern.");
    await dialog.getByRole("button", { name: "Record decision" }).click();
    await expect(dialog).toBeHidden();
  });
});

test.describe("comparison", () => {
  test("compare is offered only once there is something to compare against", async ({ page }) => {
    await page.goto("/architecture");
    await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });
    // The estate has no peer to compare with; the control says so rather than hiding.
    await expect(page.getByRole("radio", { name: "Compare", exact: true })).toBeDisabled();
  });

  test("two applications are compared on the same frame", async ({ page }) => {
    await page.goto("/applications");
    const first = page.locator('a[href^="/applications/"]').first();
    await expect(first).toBeVisible({ timeout: 15_000 });
    const href = await first.getAttribute("href");
    await page.goto(`${href}/canvas`);
    await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });

    const compare = page.getByRole("radio", { name: "Compare", exact: true });
    await expect(compare).toBeEnabled();
    await compare.click();

    const baseline = page.getByLabel("Baseline application");
    await expect(baseline).toBeVisible();
    await baseline.selectOption({ index: 1 });

    // Same canonical geometry on both sides: that is what makes a difference real.
    await expect(page.locator('[role="gridcell"]')).toHaveCount(43);
    await expectNoSeriousAccessibilityViolations(page);
  });
});
