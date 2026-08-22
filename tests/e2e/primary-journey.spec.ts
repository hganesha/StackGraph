import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// [route, page <h1>, left-rail link label] — the rail label is not always the heading.
const primaryRoutes = [
  ["/estate", "Software Estate", "Estate"],
  ["/applications", "Applications", "Applications"],
  ["/technologies", "Technologies", "Technologies"],
  ["/modernization", "Modernization", "Modernization"],
  ["/ask", "Insights", "Insights"],
] as const;

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  // On a soft navigation Next swaps the head asynchronously, so <title> can be
  // momentarily empty. Settle it first or axe reports a spurious document-title
  // violation on the slower engines.
  await expect(page).toHaveTitle(/.+/);
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

  for (const [route, heading, navLabel] of primaryRoutes) {
    if (testInfo.project.name === "mobile") {
      await page.goto(route);
    } else {
      // Exact: "Estate" would otherwise also match the "Estate Health" rail item.
      await page.getByRole("link", { name: navLabel, exact: true }).click();
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

test("explicit light and dark themes remain accessible", async ({ page }) => {
  await page.goto("/estate");
  const theme = page.getByRole("button", { name: "Theme: system" });
  await theme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("link", { name: "Business Map" })).toHaveCSS(
    "color",
    "rgb(78, 77, 73)",
  );
  await expectNoSeriousAccessibilityViolations(page);
  await page.getByRole("button", { name: "Theme: light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("link", { name: "Business Map" })).toHaveCSS(
    "color",
    "rgb(180, 178, 170)",
  );
  await expectNoSeriousAccessibilityViolations(page);
});

test("the about surface introduces the product and stays accessible", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1, name: "About StackGraph" })).toBeVisible();
  // Every namespace is described, so the domain glyphs always have a text label beside them.
  for (const domain of ["Business", "Enterprise", "Technology", "OSS", "Deployment", "Intelligence"]) {
    await expect(page.getByRole("heading", { level: 3, name: new RegExp(`^${domain}`) })).toBeVisible();
  }
  await expectNoSeriousAccessibilityViolations(page);
  await page.getByRole("link", { name: /Software Estate/ }).click();
  await expect(page).toHaveURL(/\/estate$/);
  await expect(page.getByRole("heading", { level: 1, name: "Software Estate" })).toBeVisible();
});

test("live source failure is announced without losing the application shell", async ({ page }) => {
  test.skip(process.env.E2E_DATA_SOURCE !== "live", "requires the live API client");
  await page.route("**/api/v1/estate**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ code: "PILOT_SOURCE_FAILURE", message: "injected failure" }),
    });
  });
  await page.goto("/estate");
  await expect(
    page.getByRole("alert").filter({ hasText: "Couldn’t load the estate summary" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
});
