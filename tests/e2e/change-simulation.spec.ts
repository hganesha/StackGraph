import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoSeriousAccessibilityViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(({ impact }) => impact === "serious" || impact === "critical");
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

async function openCommand(page: Page) {
  await page.getByRole("button", { name: "Plan an estate-backed change" }).click();
  const dialog = page.getByRole("dialog", { name: "Plan an estate-backed change" });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function compileGuidedChange(page: Page) {
  const dialog = await openCommand(page);
  await dialog.getByRole("button", { name: /Upgrade Package/ }).click();
  const input = dialog.getByRole("textbox", { name: "Search estate subjects" });
  await input.fill("Newtonsoft.Json");
  await dialog.getByRole("button", { name: /Newtonsoft\.Json pkg:nuget\/Newtonsoft\.Json 171 dependents/ }).click();
  await dialog.getByRole("radio", { name: /14\.0\.1 NuGet/ }).click();
  await dialog.getByRole("radio", { name: /ESTATE Entire estate 382 affected/ }).click();
  await expect(dialog.getByRole("figure", { name: /Current version spread/ })).toContainText("143");
  await dialog.getByRole("button", { name: "Compile change" }).click();
  await expect(dialog.getByRole("heading", { name: "Mutation ready" })).toBeVisible();
  return dialog;
}

test("guided compilation produces canonical tokens and a durable simulation", async ({ page }) => {
  await page.goto("/simulate");
  await expect(page.getByRole("heading", { level: 1, name: /Know the impact/ })).toBeVisible();
  const dialog = await compileGuidedChange(page);
  await expect(dialog.getByText("Newtonsoft.Json", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Resolved", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Simulate" }).click();
  await expect(page).toHaveURL(/\/simulations\/[0-9a-f-]+$/);

  await expect(page.getByRole("heading", { level: 1, name: "Simulation completed" })).toBeVisible({ timeout: 8_000 });
  await expect(page.getByRole("heading", { name: "Classification ring" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Attenuation funnel" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Found" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interpreted" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How this result can be reproduced" })).toBeVisible();
  // The hash is truncated on screen — 71 characters of machine output would dominate the
  // card — and carried in full on the title, which is the stronger assertion of the two.
  await expect(
    page.getByTitle("sha256:b4ab02f3ce73b09823d39f66fba267ba2c91887bb0daf0d276ed982d35344296", { exact: true }),
  ).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("ungrounded and ambiguous commands refuse instead of guessing", async ({ page }) => {
  await page.goto("/estate");
  let dialog = await openCommand(page);
  const command = dialog.getByRole("textbox", { name: "Type a bounded change command" });
  await command.fill("upgrade tree to 1.0.0 in estate");
  await command.press("Enter");
  await expect(dialog.getByRole("alert")).toContainText("SUBJECT_NOT_RESOLVED");
  await expect(dialog.getByText(/No estate entity matches/, { exact: true }).first()).toBeVisible();

  await dialog.getByRole("button", { name: "Start over" }).click();
  await command.fill("upgrade Newtonsoft.Json to 14.0.1 in estate");
  await command.press("Enter");
  await expect(dialog.getByText(/3 candidates/)).toBeVisible();
  await expect(dialog.getByRole("alert")).toContainText("Choose one exact canonical package");
  await expectNoSeriousAccessibilityViolations(page);
});

test("limited, not-simulatable, failed, cancelled, quarantined, AI-off, and replay are distinct", async ({ page }) => {
  const cases = [
    ["2", "Completed with reduced coverage", "PARTIAL_SCAN"],
    ["3", "This change cannot be simulated", "GRAPH_WATERMARK_STALE"],
    ["4", "Simulation failed", "WORKER_FAILURE"],
    ["5", "Simulation cancelled", "RUN_CANCELLED"],
  ] as const;
  for (const [suffix, heading, reason] of cases) {
    await page.goto(`/simulations/25000000-0000-4000-8000-00000000000${suffix}`);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByText(reason).first()).toBeVisible();
  }

  await page.goto("/simulations/25000000-0000-4000-8000-000000000006");
  await expect(page.getByText("Interpretation quarantined")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Found" })).toBeVisible();

  await page.goto("/simulations/25000000-0000-4000-8000-000000000007");
  await expect(page.getByText("Interpretation unavailable")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Found" })).toBeVisible();

  await page.goto("/simulations/25000000-0000-4000-8000-000000000008");
  await expect(page.getByText(/Existing idempotent run/)).toBeVisible();
  // Stated once more in the provenance card, where a reader checking reproducibility
  // needs to know the result was returned rather than recomputed.
  await expect(page.getByText(/Returned from an earlier identical run/)).toBeVisible();
});

test("a queued simulation can be cancelled and remains readable", async ({ page }) => {
  await page.goto("/simulate");
  const dialog = await compileGuidedChange(page);
  await dialog.getByRole("button", { name: "Simulate" }).click();
  const cancel = page.getByRole("button", { name: "Cancel run" });
  await expect(cancel).toBeVisible();
  await cancel.click();
  await expect(page.getByRole("heading", { level: 1, name: "Simulation cancelled" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How this result can be reproduced" })).toBeVisible();
});

test("command surface reflows at 200% equivalent width and closes with Escape", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 720 });
  await page.goto("/simulate");
  const dialog = await openCommand(page);
  await expect(dialog).toHaveJSProperty("scrollWidth", await dialog.evaluate((node) => node.clientWidth));
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("Change Brief print layout removes application chrome", async ({ page }) => {
  await page.goto("/simulations/25000000-0000-4000-8000-000000000001");
  await expect(page.getByRole("heading", { level: 1, name: "Simulation completed" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Change Brief" })).toBeHidden();

  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("heading", { level: 1, name: "Change Brief" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Print Change Brief" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Found" })).toBeVisible();
});
