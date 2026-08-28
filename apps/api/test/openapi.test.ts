/**
 * The document must describe the API, and the committed copy must be current.
 *
 * There is a specific failure this file exists to prevent. Plain `.get()`
 * handlers keep working on an `OpenAPIHono` — they route, they respond, every
 * other test stays green — but they do not appear in the generated document.
 * So a half-finished migration produces a document that is confidently wrong
 * about which endpoints exist, and nothing about it looks broken. The first
 * conversion here documented fourteen of twenty-nine paths and every existing
 * test passed.
 *
 * The gate is therefore not "the document parses". It is "every path the
 * registry declares is in the document", checked against the registry that the
 * router is itself checked against in `registry.test.ts`.
 */

import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import committed from "../../../contracts/openapi.json";
import { ENDPOINTS } from "../src/routes/registry";
import { ERROR_CODES } from "../src/http/schemas";

type Document = {
  openapi: string;
  info: { title: string; version: string };
  paths: Record<string, Record<string, unknown>>;
  components?: { schemas?: Record<string, unknown> };
};

async function served(): Promise<Document> {
  const response = await SELF.fetch("https://api.test/openapi.json");
  expect(response.status).toBe(200);
  return (await response.json()) as Document;
}

describe("the document describes the whole API", () => {
  it("documents every path the registry declares", async () => {
    const document = await served();
    const documented = new Set(Object.keys(document.paths));
    const missing = ENDPOINTS.map((e) => e.path).filter((path) => !documented.has(path));

    expect(
      missing,
      `declared in the registry but absent from the document — these are almost ` +
        `certainly still plain .get() handlers: ${missing.join(", ")}`
    ).toEqual([]);
  });

  it("documents nothing the registry does not declare", async () => {
    const document = await served();
    const declared = new Set(ENDPOINTS.map((e) => e.path));
    const extra = Object.keys(document.paths).filter((path) => !declared.has(path));

    expect(extra, `documented but undeclared: ${extra.join(", ")}`).toEqual([]);
  });

  it("gives every operation a summary and at least one response", async () => {
    // A document that lists a path and says nothing about it is worse than an
    // absent one: it reads as complete.
    const document = await served();
    for (const [path, methods] of Object.entries(document.paths)) {
      for (const [method, operation] of Object.entries(methods)) {
        const op = operation as { summary?: string; responses?: Record<string, unknown> };
        expect(
          op.summary?.length ?? 0,
          `${method.toUpperCase()} ${path} has no summary`
        ).toBeGreaterThan(10);
        expect(
          Object.keys(op.responses ?? {}).length,
          `${method.toUpperCase()} ${path} documents no responses`
        ).toBeGreaterThan(0);
      }
    }
  });

  it("describes the error shape wherever it can answer with one", async () => {
    // Every non-2xx in this API is problem+json, with one deliberate exception.
    // A path documenting a 404 with a bare description tells a client the
    // request can fail and nothing about how to read the failure.
    //
    // /health answers 503 with its own schema rather than a problem document,
    // and that is the right call: a monitor polls one URL and needs one shape
    // back whatever the status, and the degraded body names which dependency
    // failed and how slowly. A problem document would replace that with prose.
    // Exempted by name rather than by a rule loose enough to let the next one
    // through silently.
    const SHAPES_ITS_OWN_FAILURE = new Set(["/health"]);

    const document = await served();
    for (const [path, methods] of Object.entries(document.paths)) {
      if (SHAPES_ITS_OWN_FAILURE.has(path)) continue;
      for (const [method, operation] of Object.entries(methods)) {
        const responses = (operation as { responses: Record<string, { content?: object }> })
          .responses;
        for (const [status, response] of Object.entries(responses)) {
          if (Number(status) < 400) continue;
          expect(
            Object.keys(response.content ?? {}),
            `${method.toUpperCase()} ${path} ${status} does not declare a body`
          ).toContain("application/problem+json");
        }
      }
    }
  });
});

describe("the committed contract is current", () => {
  it("matches the document the app serves", async () => {
    // `info.version` is deliberately excluded. The served document reports the
    // data snapshot it is serving, which is a property of the deployment; the
    // committed one carries a fixed version, because otherwise every re-export
    // of the data would show up as a change to the API contract. What must not
    // differ is the surface: paths, operations and schemas.
    const document = await served();
    const shape = ({ paths, components }: Document) => ({ paths, components });

    expect(
      shape(document),
      "contracts/openapi.json is stale. Run `npm run gen` and commit the result."
    ).toEqual(shape(committed as unknown as Document));
  });

  it("is a 3.1 document", () => {
    expect((committed as unknown as Document).openapi).toMatch(/^3\.1/);
  });
});

describe("the error catalogue reaches the document", () => {
  it("names every code somewhere in the served surface", async () => {
    // ROUTE_NOT_FOUND and INTERNAL_ERROR are raised by the app's notFound and
    // onError boundaries rather than by any single route, so they are the two
    // that cannot appear under a path. Every other code belongs to a handler.
    const boundaryOnly = new Set(["ROUTE_NOT_FOUND", "INTERNAL_ERROR"]);
    const document = JSON.stringify(await served());

    const absent = Object.keys(ERROR_CODES)
      .filter((code) => !boundaryOnly.has(code))
      .filter((code) => !document.includes(code));

    expect(
      absent,
      `catalogued but never reachable through a documented path: ${absent.join(", ")}`
    ).toEqual([]);
  });
});
