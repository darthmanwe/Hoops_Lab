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
