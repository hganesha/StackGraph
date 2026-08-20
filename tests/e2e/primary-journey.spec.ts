import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const primaryRoutes = [
  ["/estate", "Software Estate"],
  ["/applications", "Applications"],
  ["/technologies", "Technologies"],
  ["/modernization", "Modernization"],
  ["/ask", "Ask your estate"],
] as const;

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.filter(({ impact }) =>
    impact === "serious" || impact === "critical"
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test("five primary surfaces form a keyboard-accessible evidence journey", async ({ page }, testInfo) => {
  await page.goto("/estate");
  await expect(page.getByRole("heading", { level: 1, name: "Software Estate" })).toBeVisible();

  const skip = page.getByRole("link", { name: "Skip to content" });
  if (testInfo.project.name === "chromium" || testInfo.project.name === "firefox") {
    await page.keyboard.press("Tab");
  } else {
    // Mobile emulation has no hardware keyboard and macOS WebKit follows the
    // host's full-keyboard-access setting. This still verifies focusability;
    // the desktop projects verify actual tab order.
    await skip.focus();
  }
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page.locator("main#main")).toBeVisible();

  for (const [route, heading] of primaryRoutes) {
    if (testInfo.project.name === "mobile") {
      await page.goto(route);
    } else {
      await page.getByRole("link", { name: heading === "Ask your estate" ? "Ask" : heading }).click();
    }
    await expect(page).toHaveURL(new RegExp(`${route.replace("/", "\\/")}$`));
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expectNoSeriousAccessibilityViolations(page);
  }

  await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
  await expect(page).toHaveURL(/\/ask$/);
});

test("reduced motion and narrow viewport preserve the primary navigation", async ({ page }) => {
  await page.goto("/estate");
  await page.setViewportSize({ width: 390, height: 844 });
  const menu = page.getByRole("button", { name: /navigation/i }).first();
  await menu.click();
  await expect(page.getByRole("link", { name: "Applications" })).toBeVisible();
  await page.getByRole("link", { name: "Applications" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Applications" })).toBeVisible();
});
