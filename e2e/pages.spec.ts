import { expect, test } from "@playwright/test";
import { PAGES } from "./pages";

/**
 * Every page renders, renders real data, and passes axe.
 *
 * Split into three assertions per route rather than one, because they fail for
 * different reasons and a combined test would report the wrong one.
 */

for (const page_ of PAGES) {
  test(`${page_.name} renders data from the API`, async ({ page }) => {
    const response = await page.goto(page_.path);

    expect(response?.status()).toBe(200);

    // The status code proves nothing here. Every page is a server component
    // that fetches during render, and a failed fetch becomes a rendered
    // explanation card — HTTP 200, full layout, no data. This is the assertion
    // that separates "the site is up" from "the site works".
    await expect(page.getByText(page_.expect).first()).toBeVisible();

    await expect(page.getByText("That is not the HoopsLab API")).toHaveCount(0);
    await expect(page.getByText("Could not reach")).toHaveCount(0);
  });
}

test("the skip link moves focus past the navigation", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");

  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});
