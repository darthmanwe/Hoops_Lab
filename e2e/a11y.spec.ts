import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { PAGES } from "./pages";

/**
 * Every page, scanned by axe, failing on serious and critical.
 *
 * Phase 5 was marked done in the roadmap against the exit criterion "axe clean
 * at serious/critical on every page". Nothing had ever run axe. This is that
 * check, arriving after the claim rather than before it.
 *
 * Minor and moderate violations are reported but not failed. They are largely
 * advisory — landmark preferences, heading-order suggestions — and a gate that
 * fails on all four levels gets its threshold quietly lowered the first time it
 * blocks something. These two levels are the ones that stop a person using the
 * page.
 */

const BLOCKING = ["serious", "critical"];

/**
 * Phone width as well as desktop, because two of the defects this suite was
 * written to find only exist at one of them. The tables are `min-w-[36rem]`,
 * so at 1280px nothing overflows and the scrollable-region rules have nothing
 * to fire on. Scanning only the wide viewport reported a clean bill of health
 * for a layout that had never been checked at the width most people read on.
 */
const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "phone", width: 375, height: 720 },
];

for (const page_ of PAGES) {
  for (const viewport of VIEWPORTS) {
    test(`${page_.name} has no serious accessibility violations on ${viewport.name}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(page_.path);
      // Wait for the real content, so axe scans the page rather than a shell.
      await expect(page.getByText(page_.expect).first()).toBeVisible();

      // No tag filter. Restricting to the WCAG tags hides axe's best-practice
      // rules, and that is how an empty `<th>` on the projections table went
      // unreported: real, trivially fixable, and outside wcag2aa. They are
      // reported here and still do not fail the build unless serious.
      const { violations } = await new AxeBuilder({ page }).analyze();

      const blocking = violations.filter((v) => BLOCKING.includes(v.impact ?? ""));

      // Attached rather than only asserted: the failure message names the rule,
      // and the attachment names every element it fired on.
      if (violations.length > 0) {
        await testInfo.attach("axe-violations.json", {
          body: JSON.stringify(violations, null, 2),
          contentType: "application/json",
        });
      }

      expect(
        blocking.map((v) => `${v.id} (${v.impact}) on ${v.nodes.length} element(s): ${v.help}`),
        `${page_.path} at ${viewport.width}px has blocking accessibility violations`
      ).toEqual([]);
    });
  }
}
