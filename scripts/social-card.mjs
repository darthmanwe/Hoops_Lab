/**
 * Render the GitHub/LinkedIn social preview card.
 *
 * GitHub crops a social preview to 2:1 and renders it small — often under
 * 600px wide in a link unfurl. Cropping a page screenshot to that shape either
 * loses the part that mattered or produces a wall of 8px table text, so the
 * card is composed for the size it will actually be seen at.
 *
 * Every figure on it is read from the committed run log rather than typed in.
 * The README spent a release quoting a model that had moved underneath it; a
 * marketing asset is the last place that should be allowed to happen again,
 * because it is the one artifact nobody re-reads.
 *
 * Usage: node scripts/social-card.mjs [outfile]
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUT = process.argv[2] ?? "docs/social-preview.png";

// -- figures, from the run log ------------------------------------------------

const runDir = "services/ml/runs/translation";
const latest = fs
  .readdirSync(runDir)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .at(-1);
if (!latest) throw new Error(`no committed training run in ${runDir}`);

const run = JSON.parse(fs.readFileSync(path.join(runDir, latest), "utf8"));
const usg = run.metrics.usg_pct;
const ts = run.metrics.ts_pct;

/** The baseline the model is judged against is the best one, not a chosen one. */
const best = (block) => Object.entries(block.baseline_mae).reduce((a, b) => (a[1] <= b[1] ? a : b));

const [, usgBaseline] = best(usg);
const [, tsBaseline] = best(ts);
const usgSkill = ((usgBaseline - usg.mae) / usgBaseline) * 100;
const tsSkill = ((tsBaseline - ts.mae) / tsBaseline) * 100;

const rate = (x) => x.toFixed(4);
const pct = (x) => `${Math.abs(x).toFixed(1)}%`;

// The test count is read from the README so the two cannot disagree.
const readme = fs.readFileSync("README.md", "utf8");
const tests = readme.match(/tests-(\d+)%20offline/)?.[1] ?? "";

const html = `<!doctype html>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; }
  body {
    width: 1280px; height: 640px; padding: 68px 72px;
    display: flex; flex-direction: column; justify-content: space-between;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    color: #f1f5f9;
    background:
      radial-gradient(circle at 18% 15%, rgba(245,161,79,0.13), transparent 28%),
      radial-gradient(circle at 84% 8%, rgba(91,160,255,0.13), transparent 32%),
      linear-gradient(120deg, #090f1f, #04050b);
  }
  .eyebrow {
    font-size: 19px; font-weight: 600; letter-spacing: 0.22em;
    text-transform: uppercase; color: #f8ba7b;
  }
  h1 { font-size: 60px; line-height: 1.06; font-weight: 700; margin-top: 20px; letter-spacing: -0.02em; }
  .sub { font-size: 25px; line-height: 1.4; color: #cbd5e1; margin-top: 20px; max-width: 1000px; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .card {
    border: 1px solid rgba(255,255,255,0.11); border-radius: 18px;
    background: rgba(255,255,255,0.05); padding: 22px 24px;
  }
  .label {
    font-size: 15px; font-weight: 600; letter-spacing: 0.13em;
    text-transform: uppercase; color: #94a3b8;
  }
  .value { font-size: 40px; font-weight: 700; margin-top: 8px; letter-spacing: -0.01em; }
  .note { font-size: 18px; line-height: 1.32; color: #cbd5e1; margin-top: 8px; }
  .miss .value, .miss .note { color: #fbbf24; }
  footer { display: flex; justify-content: space-between; align-items: baseline; font-size: 21px; color: #94a3b8; }
  footer b { color: #f1f5f9; font-weight: 600; }
</style>
<body>
  <div>
    <div class="eyebrow">HoopsLab</div>
    <h1>How basketball production<br>travels between leagues</h1>
    <p class="sub">
      EuroLeague, NBA and G League — estimated from ${usg.n_pairs} real transfers,
      with the sample size and the width of the error bars stated up front.
    </p>
  </div>

  <div class="stats">
    <div class="card">
      <div class="label">Usage rate</div>
      <div class="value">${rate(usg.mae)}</div>
      <div class="note">out-of-fold MAE — beats the best baseline by ${pct(usgSkill)}</div>
    </div>
    <div class="card miss">
      <div class="label">True shooting</div>
      <div class="value">${rate(ts.mae)}</div>
      <div class="note">loses to the league average by ${pct(tsSkill)} — and ships that verdict</div>
    </div>
    <div class="card">
      <div class="label">Reproducibility</div>
      <div class="value">${tests} tests</div>
      <div class="note">every number refits from committed data, no network</div>
    </div>
  </div>

  <footer>
    <span><b>github.com/darthmanwe/Hoops_Lab</b></span>
    <span>Python · statsmodels · Cloudflare Workers · Next.js</span>
  </footer>
</body>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
await page.setContent(html, { waitUntil: "load" });
fs.mkdirSync(path.dirname(OUT), { recursive: true });
await page.screenshot({ path: OUT });
await browser.close();

const { size } = fs.statSync(OUT);
console.log(`${OUT}  1280x640  ${(size / 1024).toFixed(0)} KB`);
if (size > 1024 * 1024) throw new Error("over GitHub's 1 MB social preview limit");
