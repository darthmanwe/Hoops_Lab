# 10. The interface is checked in both themes, by measurement rather than by sampling

Accepted.

## Context

Phase 5's exit criterion was "axe clean at serious/critical on every page". It
was marked done. Nothing had ever run axe. When it was finally run it found
keyboard-unreachable scroll regions, an empty table header, four meanings
carried only by `title=`, four places where colour was the only signal, six
pages sharing one `<title>`, and the em dash used for missing data — which had
no accessible name and was rendered in the one colour on the site that failed
WCAG AA.

Running axe is necessary and not sufficient. Axe reports a violation per element
it manages to evaluate and skips anything it considers indeterminate: a gradient
behind the text, a translucent surface, an element whose background it cannot
resolve. This site's entire surface system is `bg-white/5` over a gradient,
which is exactly the case axe marks _incomplete_ and moves past. An axe-clean
report on this layout is compatible with unreadable text.

A light theme sharpens the problem. Light mode is not a separate feature with
separate tests; it is the same pages, and the way it breaks is by rendering
something unreadable rather than by throwing. Every link on the site is the
accent colour, and the dark theme's accent is a pale orange sitting at roughly
1.6:1 on white. An inversion that reused it would pass a glance, pass every
functional test, and fail a reader.

## Decision

**Contrast is measured numerically, on every text-bearing leaf node, in both
colour schemes.** `e2e/contrast.spec.ts` walks the DOM, resolves the nearest
ancestor that actually paints, computes the WCAG ratio against the AA threshold
for that text's size and weight, and fails with the offending colour, size,
weight, element count and a sample of the text. Axe still runs, at desktop and
phone widths, with no tag filter, failing on serious and critical — this
measurement catches what its sampling skips, and does not replace it.

Supporting decisions:

- **Both themes are Playwright projects**, `dark` and `light`, running the whole
  suite rather than a light-specific subset.
- **Colours are converted through a canvas, not parsed.** The app emits `lab()`
  values, and an earlier version of this measurement read `lab(96.3 …)` as
  `rgb(96, …)` — turning light text near-black and reporting eight failures that
  did not exist. Painting the colour and reading the pixel back asks the browser
  what it actually rendered.
- **A page that yields no samples fails.** `expect(samples.length)` guards the
  case where a selector or theme change makes the check silently measure
  nothing, which is how a gate goes quiet without going red.
- **Axe scans at phone width as well as desktop.** The tables are
  `min-w-[36rem]`, so at 1280px nothing overflows and the scrollable-region
  rules have nothing to fire on. Scanning only the wide viewport reported a
  clean bill of health for a layout never checked at the width most people read
  on.
- **Minor and moderate axe violations are reported, not failed.** A gate that
  fails on all four levels gets its threshold quietly lowered the first time it
  blocks something.

## Consequences

- The theme layer had to become real before it could be measured. The previous
  palette lived in a v3-style `tailwind.config.js` reached through `@config`,
  which Tailwind compiles to literal hex — the built stylesheet contained
  `.text-court-300{color:#f8ba7b}` with no variable anywhere. There was nothing
  to swap. Hence `@theme` for the fixed palette and `@theme inline` for the
  semantic tokens: without `inline`, the utility carries the dark value forever
  and no media query can move it.
- The palette gained two darker accent steps (`court-700`, `court-800`) that
  exist only because light mode needed a shade that could carry a link. The
  accent steps down two stops rather than being reused.
- The suite is 64 browser tests across the two projects, and roughly doubles in
  cost for the second theme. That is the price of the theme being checked rather
  than assumed.
- **No theme toggle**, deliberately. Persisting a choice and applying it before
  first paint needs `suppressHydrationWarning` and an inline pre-hydration
  script — the first client-side JavaScript in an app that has none, and the
  property that makes every page server-rendered and trivially testable.
  `prefers-color-scheme` reads a preference the reader has already expressed to
  their operating system.
