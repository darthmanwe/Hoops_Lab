import { expect, test } from "@playwright/test";
import { PAGES } from "./pages";

/**
 * Every rendered text style, measured against WCAG AA.
 *
 * Axe checks contrast too, and this does not replace it — it catches what axe's
 * sampling misses. Axe reports a violation per element it happens to evaluate
 * and skips anything it considers indeterminate (a gradient behind the text, a
 * translucent surface, an element it cannot resolve a background for). This
 * page's entire surface system is `bg-white/5` over a gradient, which is
 * precisely the case axe marks incomplete and moves past.
 *
 * So this walks every text-bearing leaf node, resolves the real composited
 * background, and computes the ratio. It runs under both `colorScheme`
 * projects, which is the point: a light theme that inverts the background
 * without re-stepping the accent ramp fails here and nowhere else.
 *
 * Colours are converted through a canvas rather than parsed. The app emits
 * `lab()` values, and an earlier version of this measurement read `lab(96.3 …)`
 * as `rgb(96, …)` — turning light text into near-black and reporting eight
 * failures that did not exist. Painting the colour and reading the pixel back
 * asks the browser what it actually rendered.
 */

type Sample = {
  ratio: number;
  required: number;
  colour: string;
  size: number;
  weight: string;
  sample: string;
  count: number;
};

async function measure(page: import("@playwright/test").Page): Promise<Sample[]> {
  return page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("no 2d context");

    const toRgb = (css: string): [number, number, number, number] => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = css;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0] as number, d[1] as number, d[2] as number, (d[3] as number) / 255];
    };

    const luminance = (c: number[]): number => {
      const [r, g, b] = c.slice(0, 3).map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      }) as [number, number, number];
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };

    /** The nearest ancestor that actually paints, which is what the text sits on. */
    const backgroundOf = (element: Element): number[] => {
      let node: Element | null = element;
      while (node) {
        const painted = toRgb(getComputedStyle(node).backgroundColor);
        if (painted[3] > 0.5) return painted;
        node = node.parentElement;
      }
      return toRgb(getComputedStyle(document.body).backgroundColor);
    };

    const seen = new Map<string, Sample>();

    for (const element of document.querySelectorAll("*")) {
      const text = (element.textContent ?? "").trim();
      // Leaf nodes only: a wrapper reports its child's text against its own
      // colour, which is a style combination nobody actually sees.
      if (!text || element.children.length > 0) continue;

      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden") continue;
      if (element.closest(".sr-only") || style.clip === "rect(0px, 0px, 0px, 0px)") continue;

      const foreground = luminance(toRgb(style.color));
      const background = luminance(backgroundOf(element));
      const ratio =
        (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);

      const size = parseFloat(style.fontSize);
      const bold = parseInt(style.fontWeight, 10) >= 700;
      const large = size >= 24 || (size >= 18.66 && bold);

      const key = `${style.color}|${style.fontSize}|${style.fontWeight}`;
      const existing = seen.get(key);
      if (existing) {
        existing.count += 1;
        continue;
      }
      seen.set(key, {
        ratio: Math.round(ratio * 100) / 100,
        required: large ? 3 : 4.5,
        colour: style.color,
        size,
        weight: style.fontWeight,
        sample: text.slice(0, 40),
        count: 1,
      });
    }

    return [...seen.values()];
  });
}

for (const page_ of PAGES) {
  test(`${page_.name} meets AA contrast`, async ({ page }) => {
    await page.goto(page_.path);
    await expect(page.getByText(page_.expect).first()).toBeVisible();

    const samples = await measure(page);

    // A page that yields no samples passes without measuring anything, which
    // is how this check would go quiet if the selector or the theme changed.
    expect(samples.length, "measured no text at all").toBeGreaterThan(3);

    const failures = samples
      .filter((s) => s.ratio < s.required)
      .map(
        (s) =>
          `${s.ratio}:1 (needs ${s.required}) — ${s.colour} at ${s.size}px/${s.weight}, ` +
          `${s.count} element(s), e.g. "${s.sample}"`
      );

    expect(failures, `${page_.path} has text below WCAG AA`).toEqual([]);
  });
}
