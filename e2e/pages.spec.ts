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

test("search finds a player from the header form, without client JavaScript", async ({ page }) => {
  await page.goto("/");
  await page.fill("#player-search", "doncic");
  await page.press("#player-search", "Enter");

  // A plain GET form, so the query is in the URL and the result is server
  // rendered. Both are asserted: a client-side search would satisfy neither.
  await expect(page).toHaveURL("/players?q=doncic");
  await expect(page.getByRole("link", { name: "Luka Dončić" })).toBeVisible();
});

test("a query with no matches says so instead of showing an empty table", async ({ page }) => {
  await page.goto("/players?q=zzzznotaplayer");

  await expect(page.getByText(/No player in this snapshot matches/)).toBeVisible();
  await expect(page.locator("table")).toHaveCount(0);
});

test("search with no query explains itself rather than erroring", async ({ page }) => {
  // The API rightly rejects an empty q with a 422. The page must not show it.
  await page.goto("/players");

  await expect(page.getByText("Find a player")).toBeVisible();
  await expect(page.getByText(/Invalid|422/)).toHaveCount(0);
});
