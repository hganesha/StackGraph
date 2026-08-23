import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Service health is the screen an operator reaches for when something looks wrong, so
// it is worth asserting it stays reachable and keeps its controls. It previously lived
// two levels down under "Intelligence", where it was easy to conclude it had been
// removed.

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

test("service health is one click from Admin and lists the core stack", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("tab", { name: /Services & health/ }).click();

  // The core three are always reported, including the database.
  for (const name of ["Web UI", "API", "PostgreSQL / AGE"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  // And the workers that carry queued estate work.
  for (const name of ["GitHub webhooks", "GitHub discovery", "Graph projection"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }

  await expectNoSeriousAccessibilityViolations(page);
});

test("workspace-scoped workers can be stopped; platform-managed ones cannot", async ({ page }) => {
  await page.goto("/admin?tab=services");
  await expect(page.getByRole("heading", { level: 2, name: "Graph projection" })).toBeVisible();

  const card = (name: string) => page.locator("article").filter({ hasText: name });

  // Stopping Postgres from a UI that depends on Postgres is not the app's to offer:
  // the API marks the core tier as platform-managed, and the UI must respect that.
  await expect(card("PostgreSQL / AGE").getByRole("button")).toHaveCount(0);
  await expect(card("Graph projection").getByRole("button", { name: /Stop|Start/ })).toBeVisible();
});

test("the admin tab is deep-linkable", async ({ page }) => {
  await page.goto("/admin?tab=services");
  await expect(page.getByRole("tab", { name: /Services & health/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
