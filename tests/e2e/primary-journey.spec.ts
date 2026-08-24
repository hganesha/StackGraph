import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// [route, page <h1>, left-rail link label] — the rail label is not always the heading.
const primaryRoutes = [
  ["/estate", "Software Estate", "Estate"],
  ["/applications", "Applications", "Applications"],
  ["/technologies", "Technologies", "Technologies"],
  ["/modernization", "Modernization", "Modernization"],
  ["/ask", "Ask your estate", "Ask"],
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

  // Same caveats as the tab-order branch above: mobile emulation has no hardware
  // keyboard, and macOS WebKit routes Meta+K through the host's own key handling, so
  // the document-level shortcut never fires under automation. Chromium and Firefox
  // verify the binding for real.
  if (testInfo.project.name !== "webkit" && testInfo.project.name !== "mobile") {
    // Pressed from a surface that is not Ask. The loop above ends on /ask, and the
    // shortcut opens /ask?view=ask, so asserting from there passed only while the
    // assertion outran the navigation it was supposed to be waiting for.
    await page.getByRole("link", { name: "Estate", exact: true }).click();
    await expect(page).toHaveURL(/\/estate$/);
    // A freshly-clicked nav link means the keydown can land on the outgoing document
    // and be lost. Settle focus on the new one, then retry the press rather than
    // asserting once — the binding is what is under test, not the timing.
    await page.locator("main#main").click({ position: { x: 2, y: 2 } });
    const shortcut = process.platform === "darwin" ? "Meta+k" : "Control+k";
    await expect(async () => {
      await page.keyboard.press(shortcut);
      await expect(page).toHaveURL(/\/ask\?view=ask$/, { timeout: 1_500 });
    }).toPass({ timeout: 10_000 });
  }
  // And again from Ask itself, where it should hold the surface rather than bounce.
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page).toHaveURL(/\/ask\?view=ask$/);
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
  // This is a focused rendering interaction; the live backend read model is covered
  // by API integration tests, while this fixture carries the full database evidence.
  await page.route("**/api/v1/applications/00000000-0000-4000-8000-000000000201", (route) =>
    route.fulfill({
      contentType: "application/json",
      path: "packages/shared/src/fixtures/application-detail.json",
    })
  );
  await page.goto("/applications/00000000-0000-4000-8000-000000000201");
  await expect(page.getByRole("heading", { level: 1, name: "Billing API" })).toBeVisible();

  await page.getByRole("tab", { name: "Technology" }).click();
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
