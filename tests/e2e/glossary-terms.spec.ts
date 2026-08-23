import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The vocabulary is the product, so the affordance that explains it has to work by
// keyboard as well as by mouse, and must not corrupt the sentence it sits inside.

test("a term explains itself on hover and on keyboard focus", async ({ page }, testInfo) => {
  await page.goto("/architecture");
  await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });
  await page.locator('[data-cell-key="cell.experience.ui"]').getByRole("heading").click();

  const panel = page.locator('aside[aria-label$="detail"]');
  const term = panel.getByRole("button", { name: "health" });
  await expect(term).toBeVisible();

  // Closed: the definition is out of the accessibility tree, so a screen reader
  // reading the surrounding sentence does not hear it spliced in.
  await expect(term).toHaveAttribute("aria-expanded", "false");
  await expect(panel.getByRole("tooltip", { includeHidden: false })).toHaveCount(0);

  if (testInfo.project.name !== "mobile") {
    await term.focus();
    await expect(term).toHaveAttribute("aria-expanded", "true");
    await expect(panel.getByRole("tooltip")).toContainText("how healthy one area looks");

    // Escape closes it without moving focus, so it can never trap anyone.
    await page.keyboard.press("Escape");
    await expect(term).toHaveAttribute("aria-expanded", "false");
    await expect(term).toBeFocused();
  }

  await term.hover();
  await expect(term).toHaveAttribute("aria-expanded", "true");
});

test("clicking a term opens it rather than toggling it shut", async ({ page }) => {
  await page.goto("/architecture");
  await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });
  await page.locator('[data-cell-key="cell.experience.ui"]').getByRole("heading").click();

  const term = page.locator('aside[aria-label$="detail"]').getByRole("button", { name: "health" });
  // A click arrives with the pointer already over the term, so the hover has opened it.
  // Toggling here would close what the click was meant to open — and on touch, where
  // there is no hover, the click is the only way in.
  await term.click();
  await expect(term).toHaveAttribute("aria-expanded", "true");
  await term.click();
  await expect(term).toHaveAttribute("aria-expanded", "true");
});

test("the definition reads as prose wherever the term sits", async ({ page }) => {
  await page.goto("/architecture");
  await expect(page.locator('[role="gridcell"]').first()).toBeVisible({ timeout: 15_000 });
  await page.locator('[data-cell-key="cell.experience.ui"]').getByRole("heading").click();

  const term = page.locator('aside[aria-label$="detail"]').getByRole("button", { name: "health" });
  await term.click();
  // Target the tooltip this term describes, not whichever one happens to be first —
  // every Term on the panel renders one.
  const describedBy = await term.getAttribute("aria-describedby");
  const tooltip = page.locator(`#${describedBy}`);
  await expect(tooltip).toBeVisible();

  // The popover is nested wherever the term is used, including inside uppercase,
  // letter-spaced headings. Its own type must win.
  await expect(tooltip).toHaveCSS("text-transform", "none");
  await expect(tooltip).toHaveCSS("letter-spacing", "normal");
});

test("every term on the About glossary is defined", async ({ page }) => {
  await page.goto("/about");
  const heading = page.getByRole("heading", { name: "Words used throughout" });
  await expect(heading).toBeVisible();

  // One definition source, so a term cannot mean two things on two screens.
  const rows = page.locator("dl dt");
  expect(await rows.count()).toBeGreaterThan(15);
  await expect(page.getByText(/Never reported as a violation/)).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(
    ({ impact }) => impact === "serious" || impact === "critical",
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
});
