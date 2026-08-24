import { expect, test } from "@playwright/test";

const billingApplication = "/applications/00000000-0000-4000-8000-000000000201";

test("application overview exposes snapshot intelligence and explainable similarity", async ({ page }) => {
  await page.goto(billingApplication);

  const panel = page.getByRole("region", { name: "Structurally critical" });
  await expect(panel.getByRole("heading", { name: "Structurally critical" })).toBeVisible();
  await expect(panel.getByText("Upstream impact", { exact: true })).toBeVisible();
  await expect(panel.getByText("Bridge / SPOF")).toBeVisible();

  await panel.getByRole("button", { name: "View blast radius" }).click();
  const blast = page.getByRole("dialog", { name: "Blast radius" });
  await expect(blast.getByText("Affected entities")).toBeVisible();
  await blast.getByRole("button", { name: "Close blast radius" }).click();

  await panel.getByRole("button", { name: "Similar applications" }).click();
  const similarity = page.getByRole("dialog", { name: "Similar applications" });
  await expect(similarity.getByText("Ledger API", { exact: true })).toBeVisible();
  await expect(similarity.getByRole("heading", { name: "Why it matches" })).toBeVisible();
  await expect(similarity.getByRole("heading", { name: "What is different" })).toBeVisible();
  await expect(similarity.getByText("Billing and invoicing")).toBeVisible();
  await expect(similarity.getByText(/financial reconciliation/)).toBeVisible();
});

test("scan health reports graph and semantic readiness", async ({ page }) => {
  await page.goto("/health");

  await expect(page.getByRole("heading", { name: "Graph intelligence" })).toBeVisible();
  await expect(page.getByText("Projection lag")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Semantic intelligence" })).toBeVisible();
  await expect(page.getByText("Active coverage")).toBeVisible();
  await expect(page.getByText("100%")).toBeVisible();
});
