/**
 * Capture the README screenshots.
 *
 * Element-scoped rather than full-page: a 6,700px-tall page screenshot is
 * unreadable inline in a README, and cropping by hand goes stale the moment
 * the layout moves. Each shot below names the card it wants.
 *
 * Usage: node shots.mjs [outdir]   (servers must already be running)
 */
import { chromium } from "playwright";
import fs from "node:fs";

const WEB = process.env.WEB_BASE ?? "http://127.0.0.1:3710";
const OUT = process.argv[2] ?? "docs/screenshots";
fs.mkdirSync(OUT, { recursive: true });

/** `card` is the 1-indexed section on the page; null means the whole viewport. */
const SHOTS = [
  { name: "hero-translation", path: "/translation?direction=EL-%3ENBA", card: 2, maxHeight: 900 },
  { name: "model-verdict", path: "/model", card: 2 },
  { name: "scouting-report", path: "/players/nba_1629029", card: 4 },
  { name: "projections", path: "/projections", card: 3, maxHeight: 900 },
  { name: "landing", path: "/", card: null, viewport: { width: 1440, height: 1180 } },
  { name: "archetypes", path: "/archetypes", card: 3 },
  { name: "selection", path: "/", card: 4 },
  { name: "shrinkage", path: "/players/nba_1629029", card: 5 },
];

const browser = await chromium.launch();

for (const shot of SHOTS) {
  const page = await browser.newPage({
    viewport: shot.viewport ?? { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
  });
  await page.goto(WEB + shot.path, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(700);

  const file = `${OUT}/${shot.name}.png`;
  if (shot.card === null) {
    await page.screenshot({ path: file });
  } else {
    const target = page.locator("main > div > *").nth(shot.card - 1);
    await target.waitFor({ state: "visible", timeout: 15000 });
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
