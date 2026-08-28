/**
 * Ambient declarations for the test environment.
 *
 * Deliberately has no top-level `import` statements: that would make this a
 * module, and a wildcard `declare module "*.sql?raw"` is only ambient in a
 * script.
 */

/** Vite's `?raw` suffix returns the file's contents as a string. */
declare module "*.sql?raw" {
  const contents: string;
  export default contents;
}

/**
 * `import.meta.glob` is Vite's, and vitest provides it at runtime — but the
 * type ships in `vite/client`, whose ambient declarations assume a browser.
 * Pulling those into a Worker project to type one call would put `document`
 * and friends back in scope, which the eslint config goes out of its way to
 * keep out. Declaring the one member used is narrower and says so.
 */
interface ImportMeta {
  glob: (
    pattern: string,
    options: { eager: true; query: "?raw" }
  ) => Record<string, { default: string }>;
}
