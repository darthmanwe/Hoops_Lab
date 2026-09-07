/**
 * Where the two dev servers live, and a probe that says so when they do not.
 *
 * The addresses are duplicated from `playwright.config.ts` rather than imported
 * from it: importing the config into a file the config itself loads is a cycle,
 * and the ports are pinned in `wrangler.toml` and `apps/web/package.json`
 * anyway, so a single constant would not be a single source of truth either.
 */
export const WEB = "http://127.0.0.1:3710";
export const API = "http://127.0.0.1:8710";

export type Probe = { ok: true } | { ok: false; why: string };

/**
 * Whether the API is answering, and what went wrong if it is not.
 *
 * Uses `node:http` with keep-alive off rather than `fetch`. Called from
 * `global-teardown.ts`, `fetch` leaves undici's connection pool - a socket and
 * its timer - alive into Playwright's own shutdown, and Node on Windows aborts
 * with `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)` in `src/win/
 * async.c`. The suite passed all sixty-four tests and then exited 127, which
 * would have turned a green run red on the platform this project is developed
 * on. One request with no pool outlives nothing.
 */
export async function probeApi(): Promise<Probe> {
  const { get } = await import("node:http");

  const body = await new Promise<{ status: number; text: string } | Error>((resolve) => {
    const req = get(`${API}/health`, { agent: false, timeout: 5_000 }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk: string) => (text += chunk));
      res.on("end", () => resolve({ status: res.statusCode ?? 0, text }));
    });
    req.on("timeout", () => {
      req.destroy(new Error("timed out after 5s"));
    });
    req.on("error", (error) => resolve(error));
  });

  if (body instanceof Error) {
    return { ok: false, why: `${API}/health did not answer: ${body.message}` };
  }
  if (body.status !== 200) {
    return { ok: false, why: `GET ${API}/health answered ${body.status}` };
  }

  let parsed: { dependencies?: { d1?: { ok?: boolean } } };
  try {
    parsed = JSON.parse(body.text) as typeof parsed;
  } catch {
    return { ok: false, why: `${API}/health answered 200 with a body that is not JSON` };
  }

  if (parsed.dependencies?.d1?.ok !== true) {
    return {
      ok: false,
      why:
        `${API}/health answered 200 but reports D1 unreachable. ` +
        "Run `npm run db:migrate && npm run db:load:fixture` before the suite.",
    };
  }
  return { ok: true };
}
