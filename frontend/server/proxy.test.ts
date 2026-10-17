// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { forwardApi } from "./proxy.ts";

afterEach(() => vi.unstubAllEnvs());
describe("production event API proxy", () => {
  it.each([
    "",
    "http://backend.example",
    "https://user:secret@backend.example",
    "https://backend.example/api",
    "https://site.example",
  ])("rejects unsafe/missing origin %s", async (origin) => {
    vi.stubEnv("BACKEND_ORIGIN", origin);
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    expect(
      (await forwardApi(new Request("https://site.example/api/config"))).status,
    ).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("preserves canonical API path/query, caller auth and status without cookies or cache", async () => {
    vi.stubEnv("BACKEND_ORIGIN", "https://backend.example");
    const fetcher = vi.fn().mockResolvedValue(
      new Response('{"error":"unauthenticated"}', {
        status: 401,
        headers: {
          "WWW-Authenticate": "Bearer",
          "Set-Cookie": "private=secret",
        },
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const response = await forwardApi(
      new Request("https://site.example/api/events?limit=100&offset=0", {
        headers: {
          Authorization: "Bearer synthetic-jwt",
          Cookie: "private=secret",
        },
      }),
    );
    expect(String(fetcher.mock.calls[0][0])).toBe(
      "https://backend.example/api/events?limit=100&offset=0",
    );
    const options = fetcher.mock.calls[0][1];
    expect(options.headers.get("authorization")).toBe("Bearer synthetic-jwt");
    expect(options.headers.has("cookie")).toBe(false);
    expect(options.redirect).toBe("manual");
    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe("Bearer");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.has("set-cookie")).toBe(false);
  });
  it("does not follow redirects or expose connection failure details", async () => {
    vi.stubEnv("BACKEND_ORIGIN", "https://backend.example");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(null, {
            status: 307,
            headers: { Location: "https://other.example" },
          }),
        )
        .mockRejectedValueOnce(new Error("private connection details")),
    );
    expect(
      (await forwardApi(new Request("https://site.example/api/config"))).status,
    ).toBe(502);
    const failed = await forwardApi(
      new Request("https://site.example/api/config"),
    );
    expect(await failed.text()).not.toContain("private");
  });
});

it("forwards nested rewritten routes and removes only the routing parameter", async () => {
  vi.stubEnv("BACKEND_ORIGIN", "https://backend.example");
  const fetcher = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetcher);
  await forwardApi(
    new Request(
      "https://site.example/api/proxy?__backend_path=events%2Fsynthetic-id&limit=100",
    ),
  );
  expect(String(fetcher.mock.calls[0][0])).toBe(
    "https://backend.example/api/events/synthetic-id?limit=100",
  );
  const response = await forwardApi(
    new Request(
      "https://site.example/api/proxy?__backend_path=../../elsewhere",
    ),
  );
  expect(response.status).toBe(400);
});

it.each(["/mcp", "/api/mcp"])(
  "forwards the MCP protocol through %s",
  async (path) => {
    const { forwardMcp } = await import("./proxy.ts");
    vi.stubEnv("BACKEND_ORIGIN", "https://backend.example");
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response("{}", {
          headers: { "Mcp-Session-Id": "synthetic-session" },
        }),
      );
    vi.stubGlobal("fetch", fetcher);
    const response = await forwardMcp(
      new Request(`https://site.example${path}`, {
        method: "POST",
        body: "{}",
        headers: {
          Authorization: "Bearer personal",
          Accept: "application/json, text/event-stream",
          "Mcp-Protocol-Version": "2025-03-26",
        },
      }),
    );
    expect(String(fetcher.mock.calls[0][0])).toBe(
      "https://backend.example/mcp",
    );
    expect(fetcher.mock.calls[0][1].headers.get("authorization")).toBe(
      "Bearer personal",
    );
    expect(fetcher.mock.calls[0][1].headers.get("accept")).toBe(
      "application/json, text/event-stream",
    );
    expect(response.headers.get("mcp-session-id")).toBe("synthetic-session");
  },
);
