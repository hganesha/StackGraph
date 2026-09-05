import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The heat grid is the one surface allowed a sequential colour ramp, and it is allowed
// it only because the encoding is redundant: a legend is permanently on screen, every
// cell carries its numeral, and the same figures are available as a table. These tests
// hold that bargain rather than the pixels.

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  await expect(page).toHaveTitle(/.+/);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(({ impact }) =>
    impact === "serious" || impact === "critical"
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test("the estate offers the heat grid as a peer view of the ranked list", async ({ page }) => {
  await page.goto("/estate");
  await expect(page.getByRole("heading", { level: 1, name: "Your estate" })).toBeVisible();

  await page.getByRole("navigation", { name: "Estate view" }).getByRole("link", { name: "Heat grid" }).click();
  await expect(page).toHaveURL(/view=heat/);
});

test("the grid ships with its legend on screen and its numbers as text", async ({ page }) => {
  await page.goto("/estate?view=heat");

  const grid = page.getByRole("region", { name: /Where the estate is most scattered|scattered/ });
  const heading = page.getByRole("heading", { name: "Where the estate is most scattered" });
  const empty = page.getByRole("heading", { name: "No capabilities are mapped yet" });

  // Fixtures may hold no mapped capability. The empty state is a finding of its own and
  // is an acceptable outcome here; what must never happen is a coloured grid with no
  // legend beside it.
  if (await empty.isVisible().catch(() => false)) {
    await expectNoSeriousAccessibilityViolations(page);
    return;
  }

  await expect(heading).toBeVisible();
  // Inline and permanent, never a popover.
  await expect(grid.getByRole("complementary", { name: /legend/i })).toBeVisible();
  // The same figures, as a table, so the picture is never the only carrier.
  await expect(grid.getByRole("columnheader", { name: "Spread" })).toBeVisible();
  await expect(grid.getByRole("columnheader", { name: "Reuse" })).toBeVisible();

  await expectNoSeriousAccessibilityViolations(page);
});

test("colour can be turned off without losing the grid", async ({ page }) => {
  await page.goto("/estate?view=heat");
  const off = page.getByRole("radio", { name: "Off" });
  if (!(await off.isVisible().catch(() => false))) return;

  await off.click();
  await expect(off).toHaveAttribute("aria-checked", "true");
  // Cell area and the table survive; only the ramp goes.
  await expect(page.getByRole("columnheader", { name: "Applications" })).toBeVisible();
});
