import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const repository = "/repositories/00000000-0000-4000-8000-000000000203";

test("repository view summarizes intent, activity, context, and findings", async ({ page }) => {
  await page.goto(repository);

  await expect(page.getByRole("heading", { name: "What this repository does" })).toBeVisible();

  const activity = page.getByRole("region", { name: "What changed recently" });
  await expect(activity).toBeVisible();
  await expect(activity.getByText("47", { exact: true })).toBeVisible();
  await expect(activity.getByText("8", { exact: true })).toBeVisible();
  await expect(activity.getByText("@dana-okafor", { exact: true })).toBeVisible();
  await expect(page.getByText("Default branch: main")).toBeVisible();

  await activity.getByRole("button", { name: "7 days" }).click();
  await expect(activity.getByText("11", { exact: true })).toBeVisible();
  await expect(activity.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");

  await expect(page.getByRole("heading", { name: "How it fits into the estate" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show all findings" })).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    results.violations.filter(({ impact }) => impact === "serious" || impact === "critical"),
    JSON.stringify(results.violations, null, 2),
  ).toEqual([]);
});
