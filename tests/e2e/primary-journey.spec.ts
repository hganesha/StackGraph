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

test("application technology embeds deterministic data infrastructure evidence", async ({ page }) => {
  await page.goto("/applications/00000000-0000-4000-8000-000000000201");
  await expect(page.getByRole("heading", { level: 1, name: "Billing API" })).toBeVisible();

  await page.getByRole("button", { name: /Data infrastructure/ }).click();
  await page.getByRole("button", { name: /^Databases/ }).click();
  await page.getByRole("button", { name: "PostgreSQL" }).click();

  const inspector = page.getByRole("complementary", { name: "Inspecting PostgreSQL" });
  await expect(inspector).toContainText("Repository evidence");
  await expect(inspector).toContainText("Database");
  await expect(inspector).toContainText("postgresql");
  await expect(inspector).toContainText("Dependency Declaration");
  await expect(inspector).toContainText("pypi:psycopg");
  await expect(inspector).toContainText("DATABASE_URL");
  await expect(inspector.getByRole("button", { name: /Repository database evidence/ })).toBeVisible();
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  await expectNoSeriousAccessibilityViolations(page);
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
