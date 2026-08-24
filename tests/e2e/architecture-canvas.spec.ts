import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const CANVAS_CELL = '[role="gridcell"]';

// Each architecture domain is its own ARIA grid, so there are six per canvas.
async function waitForCanvas(page: Page) {
  await expect(page.locator('[role="grid"]').first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(CANVAS_CELL).first()).toBeVisible();
}

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

test.describe("architecture canvas", () => {
  test("renders the full canonical frame with every cell state legible", async ({ page }) => {
    await page.goto("/architecture");
    await expect(page.getByRole("heading", { level: 1, name: "Architecture" })).toBeVisible();
    await waitForCanvas(page);

    // Every canonical cell is rendered. A canvas that drops cells is not a fixed frame.
    const cells = page.locator(CANVAS_CELL);
    await expect(cells).toHaveCount(43);

    // All five states are represented and each carries a text label, never colour alone.
    const states = await cells.evaluateAll((nodes) =>
      [...new Set(nodes.map((node) => (node as HTMLElement).dataset.state))].sort(),
    );
    expect(states).toEqual(["EMPTY", "NOT_APPLICABLE", "POPULATED", "UNBOUND", "UNOBSERVED"]);

    // The caption states the distribution rather than an aggregate score.
    await expect(page.locator("#canvas-caption")).toContainText("43 canonical cells");
    await expect(page.locator("#canvas-caption")).toContainText("not yet modelled");

    await expectNoSeriousAccessibilityViolations(page);
  });

  test("announced grid geometry matches the rendered geometry", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    // The single most important a11y invariant here: a wrapped grid whose ARIA
    // indices describe a different shape than the one on screen is worse than no
    // grid semantics at all.
    const geometry = await page.evaluate(() => {
      const grid = document.querySelector('[role="grid"]')!;
      const row = grid.querySelector('[role="row"]')!;
      const rendered = getComputedStyle(row).gridTemplateColumns.split(" ").length;
      const announced = Number(grid.getAttribute("aria-colcount"));
      const maxColIndex = Math.max(
        ...[...document.querySelectorAll('[role="gridcell"]')].map((cell) =>
          Number(cell.getAttribute("aria-colindex")),
        ),
      );
      return { rendered, announced, maxColIndex };
    });
    expect(geometry.announced).toBe(geometry.rendered);
    expect(geometry.maxColIndex).toBeLessThanOrEqual(geometry.announced);
  });

  test("arrow keys move across cells and continue into the next band", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === "mobile", "No hardware keyboard under mobile emulation.");
    await page.goto("/architecture");
    await waitForCanvas(page);

    const first = page.locator(CANVAS_CELL).first();
    await first.focus();
    const startKey = await first.getAttribute("data-cell-key");
    expect(startKey).toBe("cell.experience.ui");

    await page.keyboard.press("ArrowRight");
    const afterRight = await page.evaluate(
      () => (document.activeElement as HTMLElement)?.dataset.cellKey,
    );
    expect(afterRight).not.toBe(startKey);

    // Enough downward moves to fall out of the first band into the second.
    for (let index = 0; index < 4; index += 1) await page.keyboard.press("ArrowDown");
    const afterDown = await page.evaluate(
      () => (document.activeElement as HTMLElement)?.dataset.cellKey,
    );
    expect(afterDown).not.toContain("cell.experience.");

    // Exactly one cell is in the tab order at a time (roving tabindex).
    const tabbable = await page.locator(`${CANVAS_CELL}[tabindex="0"]`).count();
    expect(tabbable).toBe(1);
  });

  test("versions of one package collapse into a single chip", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    const cell = page.locator('[data-cell-key="cell.experience.ui"]');
    // Three resolved Reacts and one Vue read as two packages, not four technologies.
    await expect(cell.locator("li")).toHaveCount(2);
    await expect(cell).toContainText("3 versions");

    // The headline comes from the most severe version. React's current major is
    // preferred and its oldest is prohibited; the chip must show the prohibition.
    // (The label is title-case in the DOM and uppercased by CSS.)
    await expect(cell).toContainText(/Prohibited/i);

    // Expanding happens in the panel, where each version keeps its own decision.
    await cell.getByRole("heading").click();
    const panel = page.locator('aside[aria-label$="detail"]');
    await expect(panel).toContainText("2 packages, 4 versions");
    await panel.getByText(/3 resolved versions/).click();
    await expect(panel).toContainText("React@18.3.1");
    await expect(panel).toContainText("React@16.14.0");
  });

  test("selecting a cell opens the detail panel and Escape closes it", async ({ page }, testInfo) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    const cell = page.locator('[data-cell-key="cell.experience.state"]');
    // Click the heading, not the cell's centre: the centre is covered by occupant
    // chips, and a chip click deliberately navigates to that technology instead.
    await cell.getByRole("heading").click();

    // Located by accessible name rather than landmark role: a nested <aside>'s role
    // mapping varies by engine, and the name is what a reader actually hears.
    const panel = page.locator('aside[aria-label$="detail"]');
    await expect(panel).toBeVisible();
    await expect(cell).toHaveAttribute("aria-selected", "true");

    // The panel expands what the cell had to compress, including the parts that are
    // null: an unmeasured component states why, rather than rendering blank.
    await expect(panel).toContainText("What we checked");
    await expect(panel).toContainText("Scores");
    await expect(panel).toContainText("Your standard");
    await expect(panel).toContainText("by: client-state");

    await expectNoSeriousAccessibilityViolations(page);

    if (testInfo.project.name !== "mobile") {
      await cell.focus();
      await page.keyboard.press("Escape");
      await expect(panel).toBeHidden();
    }
  });

  test("the aspect lens dims cells but never removes them", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    const before = await page.locator(CANVAS_CELL).count();
    await page.getByRole("button", { name: /Security & privacy/ }).click();

    await expect(page.locator("#canvas-caption")).toContainText("aspect lens active");
    // Comparison and lens views may not hide canonical cells (spec §5.4).
    await expect(page.locator(CANVAS_CELL)).toHaveCount(before);

    // Cell keys and aspect assignments come from the server catalog: UI rendering
    // carries no security aspect, databases do.
    // toHaveCSS retries, so this settles past the dim transition rather than racing it.
    await expect(page.locator('[data-cell-key="cell.experience.ui"]')).toHaveCSS("opacity", "0.42");
    await expect(page.locator('[data-cell-key="cell.data.database"]')).toHaveCSS("opacity", "1");

    const dimmed = await page
      .locator(CANVAS_CELL)
      .evaluateAll((nodes) => nodes.filter((n) => parseFloat(getComputedStyle(n).opacity) < 0.9).length);
    expect(dimmed).toBeGreaterThan(0);
    expect(dimmed).toBeLessThan(before);
  });

  test("drift never turns an unevaluable cell into a violation", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    await page.getByRole("radio", { name: "Drift", exact: true }).click();
    await expect(page.locator(CANVAS_CELL).first()).toBeVisible();

    const tones = await page.locator(CANVAS_CELL).evaluateAll((nodes) =>
      nodes.map((node) => ({
        state: (node as HTMLElement).dataset.state,
        tone: (node as HTMLElement).dataset.tone,
      })),
    );
    // An incomplete observation is a gap in knowledge, not non-conformance (spec §7.4).
    for (const cell of tones.filter((entry) => entry.state === "UNOBSERVED" || entry.state === "UNBOUND")) {
      expect(cell.tone).toBe("quiet");
    }
  });

  test("no horizontal page scroll at any width, and the rail reflows", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    for (const width of [1440, 1100, 820, 600, 375]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(CANVAS_CELL).first()).toBeVisible();
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return doc.scrollWidth - doc.clientWidth;
      });
      // Seeing the whole frame at once is the point; a sideways scroll defeats it.
      expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(1);

      const geometry = await page.evaluate(() => {
        const grid = document.querySelector('[role="grid"]')!;
        const row = grid.querySelector('[role="row"]')!;
        return {
          announced: Number(grid.getAttribute("aria-colcount")),
          rendered: getComputedStyle(row).gridTemplateColumns.split(" ").length,
        };
      });
      expect(geometry.announced, `column mismatch at ${width}px`).toBe(geometry.rendered);
    }
  });

  test("occupant chips stay inside their cells in the wide canvas layout", async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1290 });
    await page.goto("/architecture");
    await waitForCanvas(page);

    const chips = page.locator(`${CANVAS_CELL} li > button`);
    expect(await chips.count()).toBeGreaterThan(0);

    const overflow = await chips.evaluateAll((nodes) =>
      nodes.flatMap((node) => {
        const cell = node.closest('[role="gridcell"]');
        if (!cell) return ["chip has no grid cell"];

        const chipRect = node.getBoundingClientRect();
        const cellRect = cell.getBoundingClientRect();
        const epsilon = 0.5;
        return chipRect.left < cellRect.left - epsilon || chipRect.right > cellRect.right + epsilon
          ? [
              `${node.getAttribute("aria-label")}: chip ${chipRect.left}-${chipRect.right}, cell ${cellRect.left}-${cellRect.right}`,
            ]
          : [];
      }),
    );

    expect(overflow).toEqual([]);
  });

  test("unplaced observations are surfaced, never dropped", async ({ page }) => {
    await page.goto("/architecture");
    await waitForCanvas(page);

    const tray = page.getByRole("button", { name: /Not placed on the canvas/ });
    await expect(tray).toBeVisible();
    await tray.click();

    await expect(page.getByRole("tab", { name: /Unclassified/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Ambiguous/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Unresolved policies/ })).toBeVisible();

    await page.getByRole("tab", { name: /Ambiguous/ }).click();
    // A technology may legitimately occupy several cells; the reason must be visible.
    await expect(page.getByRole("tabpanel")).toContainText("Redis");
    await expect(page.getByRole("tabpanel")).toContainText("not mutually exclusive");
  });
});

test.describe("canvas across surfaces", () => {
  test("the estate exposes the canvas as a peer view", async ({ page }) => {
    await page.goto("/estate?view=canvas");
    await expect(page.getByRole("heading", { level: 1, name: "Software Estate" })).toBeVisible();
    await waitForCanvas(page);
    await expect(page.locator('[role="gridcell"]')).toHaveCount(43);
    await expectNoSeriousAccessibilityViolations(page);
  });

  test("an application renders the same frame from its own evidence", async ({ page }) => {
    await page.goto("/applications");
    const firstApplication = page.locator('a[href^="/applications/"]').first();
    await expect(firstApplication).toBeVisible({ timeout: 15_000 });
    const href = await firstApplication.getAttribute("href");
    await page.goto(`${href}/canvas`);

    await expect(page.getByRole("heading", { level: 1, name: /architecture canvas$/ })).toBeVisible();
    await waitForCanvas(page);
    // Same canonical geometry as the estate: that is what makes the two comparable.
    await expect(page.locator('[role="gridcell"]')).toHaveCount(43);
    await expectNoSeriousAccessibilityViolations(page);
  });
});
