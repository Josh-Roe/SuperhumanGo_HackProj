import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  loadProjectStatus,
  parseWorkspace,
  requestJson,
} from "./api";
import { createPreviewGateway } from "./preview";
import { safeUrl } from "./types";
import { localTime, toInstant } from "./dates";
describe("API boundary and revision invariants", () => {
  it("roundtrips fixture snapshots and rejects malformed review/provenance", async () => {
    const gateway = createPreviewGateway();
    const snapshot = await gateway.get("preview-gathering");
    expect(parseWorkspace(snapshot).event.revision).toBe(2);
    expect(() =>
      parseWorkspace({
        ...snapshot,
        content: [{ ...snapshot.content[0], producer: "unknown-ai" }],
      }),
    ).toThrow(/contract/);
    expect(() => parseWorkspace({ ...snapshot, facts: {} })).toThrow(
      /contract/,
    );
  });
  it("supersedes preparation on edits and rejects lost updates", async () => {
    const gateway = createPreviewGateway();
    const snapshot = await gateway.get("preview-gathering");
    const updated = await gateway.save(
      snapshot.event.id,
      { ...snapshot.event, location: "New venue" },
      2,
    );
    expect(updated.event.revision).toBe(3);
    expect(updated.review_revision).toBeNull();
    expect(updated.content[0].event_revision).toBe(2);
    expect(updated.work[0].state).toBe("awaiting_go");
    await expect(
      gateway.save(snapshot.event.id, snapshot.event, 2),
    ).rejects.toThrow(/revision_conflict/);
    await gateway.prepare(snapshot.event.id, 3);
    expect((await gateway.get(snapshot.event.id)).work).toHaveLength(1);
    await expect(
      gateway.publish(snapshot.event.id, 3, "publish", "key"),
    ).rejects.toThrow(/cannot publish/);
  });
  it.each([
    [401, "unauthenticated"],
    [403, "forbidden"],
    [409, "revision_conflict"],
    [404, "api_unavailable"],
    [503, "provider_failed"],
  ])("maps HTTP %s without exposing server internals", async (status, code) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("private server text", { status: Number(status) }),
        ),
    );
    await expect(requestJson("/api/events", "jwt")).rejects.toMatchObject({
      code,
    });
    await expect(requestJson("/api/events", "jwt")).rejects.toBeInstanceOf(
      ApiError,
    );
  });
  it("rejects invalid health and unsafe artifact links", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
    await expect(
      loadProjectStatus(new AbortController().signal),
    ).rejects.toThrow();
    expect(safeUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeUrl("http://example.com")).toBeUndefined();
    expect(safeUrl("https://example.com/flyer")).toBe(
      "https://example.com/flyer",
    );
  });
  it("interprets local wall times independently of the browser timezone and rejects DST gaps/overlaps", () => {
    expect(toInstant("2026-11-07T10:00", "America/Los_Angeles")).toBe(
      "2026-11-07T18:00:00.000Z",
    );
    expect(localTime("2026-11-07T18:00:00Z", "America/Los_Angeles")).toBe(
      "2026-11-07T10:00",
    );
    expect(() => toInstant("2026-03-08T02:30", "America/Los_Angeles")).toThrow(
      /daylight-saving/,
    );
    expect(() => toInstant("2026-11-01T01:30", "America/Los_Angeles")).toThrow(
      /daylight-saving/,
    );
    expect(toInstant("2026-11-07T10:00", "Asia/Kathmandu")).toBe(
      "2026-11-07T04:15:00.000Z",
    );
  });
});

describe("published event transfer contract", () => {
  it("uses canonical event responses with pagination and never enables writes", async () => {
    const { createEventTransferGateway } = await import("./api");
    const snapshot = await createPreviewGateway().get("preview-gathering");
    const fetcher = vi
      .fn()
      .mockImplementation((path: string) =>
        Promise.resolve(
          new Response(
            JSON.stringify(
              path.includes("?") ? [snapshot.event] : snapshot.event,
            ),
          ),
        ),
      );
    vi.stubGlobal("fetch", fetcher);
    const gateway = createEventTransferGateway("synthetic-session");
    expect((await gateway.list())[0].title).toBe(snapshot.event.title);
    expect((await gateway.get(snapshot.event.id)).event).toEqual(
      snapshot.event,
    );
    expect(fetcher.mock.calls[0][0]).toBe("/api/events?limit=100&offset=0");
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer synthetic-session",
    );
    expect(gateway.readOnly).toBe(true);
    await expect(gateway.save(null, snapshot.event)).rejects.toThrow(
      /event details only/,
    );
    await expect(
      gateway.publish(snapshot.event.id, 2, "publish", "key"),
    ).rejects.toThrow(/event details only/);
  });
  it("reports missing API registration before any account sign-in request", async () => {
    const { loadPublicAuthConfig } = await import("./api");
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 404 }));
    vi.stubGlobal("fetch", fetcher);
    await expect(loadPublicAuthConfig()).rejects.toThrow(/not registered/);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/config");
  });
});

describe("deployment readiness diagnostics", () => {
  it.each([502, 503])(
    "reports HTTP %s as deployment failure instead of missing registration",
    async (status) => {
      const { loadPublicAuthConfig } = await import("./api");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response("{}", { status })),
      );
      await expect(loadPublicAuthConfig()).rejects.toThrow(
        /deployment.*BACKEND_ORIGIN/,
      );
    },
  );
  it("explains an HTML fallback and rejects unsafe Supabase configuration before sign-in", async () => {
    const { loadPublicAuthConfig } = await import("./api");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("<!doctype html>"))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              configured: true,
              supabase_url: "ftp://localhost",
              supabase_publishable_key: "public-key",
            }),
          ),
        ),
    );
    await expect(loadPublicAuthConfig()).rejects.toThrow(
      /\/api\/config reaches/,
    );
    await expect(loadPublicAuthConfig()).rejects.toThrow(
      /invalid public Supabase/,
    );
  });
});
