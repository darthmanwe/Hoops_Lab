/**
 * Capture the README screenshots.
 *
 * Element-scoped rather than full-page: a 6,700px-tall page screenshot is
 * unreadable inline in a README, and cropping by hand goes stale the moment
 * the layout moves. Each shot below names the card it wants.
 *
 * Usage: node shots.mjs [outdir]   (servers must already be running)
 */
// From @playwright/test rather than `playwright`: the bare package was never
// declared in any package.json, so `npm ci` removed it and this script failed
// on every clean clone and in CI. The test runner re-exports the same browser.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const WEB = process.env.WEB_BASE ?? "http://127.0.0.1:3710";
const OUT = process.argv[2] ?? "docs/screenshots";
fs.mkdirSync(OUT, { recursive: true });

/**
 * `card` is the 1-indexed section on the page; null means the whole viewport.
 *
 * `expect` is a substring that must appear in the captured card. Indices go
 * stale silently when a page gains a section — `selection` spent several
 * commits pointing at the landing page's nav card while the README captioned
 * it "selection gaps per direction", which is precisely the sort of confident
 * mislabelling this project exists to remove. A wrong index now fails the run.
 */
const SHOTS = [
  {
    name: "hero-translation",
    path: "/translation?direction=EL-%3ENBA",
    card: 2,
    maxHeight: 900,
    expect: "EuroLeague → NBA",
  },
  { name: "model-verdict", path: "/model", card: 2, expect: "True shooting" },
  { name: "scouting-report", path: "/players/nba_1629029", card: 4, expect: "Scouting report" },
  { name: "projections", path: "/projections", card: 3, maxHeight: 900, expect: "eligible" },
  {
    // The counterfactual that only exists since every direction is projected,
    // and the clearest picture of what the support flag is for: rank NBA
    // players by projected EuroLeague usage and the whole top of the list is
    // extrapolation, because the players who actually left were below average.
    name: "projections-nba",
    path: "/projections?direction=NBA-%3EEL",
    card: 3,
    maxHeight: 820,
    expect: "eligible NBA players",
  },
  { name: "landing", path: "/", card: null, viewport: { width: 1440, height: 1180 } },
  { name: "archetypes", path: "/archetypes", card: 3, expect: "stability" },
  { name: "selection", path: "/", card: 3, expect: "Selection" },
  { name: "shrinkage", path: "/players/nba_1629029", card: 5, expect: "Three-point" },
  {
    // "Every historical comparable is one click away" is a claim the README
    // makes and had no picture for.
    name: "comparables",
    path: "/players/nba_1629029",
    card: 6,
    expect: "Comparables",
  },
];

const browser = await chromium.launch();

for (const shot of SHOTS) {
  const page = await browser.newPage({
    viewport: shot.viewport ?? { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
    // Pinned, and it has to be. Headless Chromium reports
    // `prefers-color-scheme: light`, which did not matter while the site was
    // dark-only and does now — the first run after the light theme landed
    // quietly re-rendered every README image in the wrong theme. Dark is what
    // the README, the hero image and the social card have always shown.
    colorScheme: "dark",
  });
  await page.goto(WEB + shot.path, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(700);

  const file = `${OUT}/${shot.name}.png`;
  if (shot.card === null) {
    await page.screenshot({ path: file });
  } else {
    const target = page.locator("main > div > *").nth(shot.card - 1);
    await target.waitFor({ state: "visible", timeout: 15000 });

    const text = await target.innerText();
    if (shot.expect && !text.includes(shot.expect)) {
      throw new Error(
        `${shot.name}: card ${shot.card} of ${shot.path} does not contain ` +
          `"${shot.expect}". It starts "${text.split("\n")[0].slice(0, 60)}". ` +
          "The page has gained or lost a section; fix the index."
      );
    }

    const box = await target.boundingBox();
    if (!box) throw new Error(`no bounding box for ${shot.name}`);
    // `fullPage` is required, not cosmetic: a clip is resolved against the
    // rendered image, and several of these cards sit below the fold, so
    // clipping a viewport-sized capture asks for a region that does not exist.
    await page.screenshot({
      path: file,
      fullPage: true,
      clip: {
        x: box.x,
        y: box.y + (await page.evaluate(() => window.scrollY)),
        width: box.width,
        height: Math.min(box.height, shot.maxHeight ?? box.height),
      },
    });
  }
  const { size } = fs.statSync(file);
  console.log(`${shot.name.padEnd(20)} ${(size / 1024).toFixed(0).padStart(5)} KB`);
  await page.close();
}

await browser.close();
