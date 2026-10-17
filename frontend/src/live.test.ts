import { backend } from "./test/organizerBackend";
import { describe, expect, it } from "vitest";

describe("published organizer REST adapter", () => {
  it("hydrates real review, authorized assets and private RSVP evidence", async () => {
    const { gateway, event, fetcher } = await backend();
    const snapshot = await gateway.get(event.id);
    expect(snapshot.content[0].kind).toBe("invitation");
    expect(snapshot.assets.map((asset) => asset.kind)).toEqual([
      "flyer",
      "document",
    ]);
    expect(snapshot.assets[0].preview_url).toContain(
      "https://storage.example/",
    );
    expect(snapshot.rsvps[0].status).toBe("attending");
    expect(JSON.stringify(snapshot)).not.toContain("DO NOT DISPLAY");
    expect(snapshot.gmail).toBeNull();
    expect(snapshot.live?.warnings.join(" ")).toContain("Gmail draft bindings");
    expect(snapshot.findings).toEqual([
      expect.objectContaining({
        category: "religious_observances",
        status: "attention",
        conflicts: ["Yom Kippur"],
      }),
    ]);
    expect(
      fetcher.mock.calls.every(
        ([, options]) =>
          options.headers.Authorization === "Bearer organizer-session",
      ),
    ).toBe(true);
  });
  it("uses PUT/full fields and strips client guest IDs while retaining display names", async () => {
    const { gateway, event, fetcher } = await backend();
    const saved = await gateway.save(
      event.id,
      { ...event, location: "New venue" },
      1,
    );
    expect(saved.event.revision).toBe(2);
    const [, options] = fetcher.mock.calls.find(([, o]) => o.method === "PUT")!;
    expect(JSON.parse(options.body)).toMatchObject({
      expected_revision: 1,
      location: "New venue",
      invitees: [{ email: "guest@example.com", display_name: "Guest" }],
    });
    expect(JSON.parse(options.body).invitees[0]).not.toHaveProperty("id");
  });
  it("queues preparation, saves edited writing through content review, then authorizes Go once", async () => {
    const { gateway, event, fetcher } = await backend();
    const queued = await gateway.prepare(event.id, 1);
    expect(queued.work[0].state).toBe("awaiting_go");
    const review = await gateway.review(
      event.id,
      1,
      queued.content.map((c) => ({ ...c, body: "Organizer revision" })),
      queued.facts,
    );
    expect(review.content[0]).toMatchObject({
      id: "organizer-mail",
      producer: "organizer",
      state: "ready",
    });
    const approved = await gateway.publish(
      event.id,
      1,
      "publish",
      "stable-key",
      "organizer-mail",
    );
    expect(approved.live?.approval?.id).toBe("approval-id");
    expect(approved.operations).toEqual([]);
    await gateway.publish(
      event.id,
      1,
      "publish",
      "stable-key",
      "organizer-mail",
    );
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith("/approvals")),
    ).toHaveLength(1);
    expect(
      fetcher.mock.calls.some(
        ([url]) => url.endsWith("/publish") || url.endsWith("/sync"),
      ),
    ).toBe(false);
  });
  it("blocks approval without attachments and never silently saves inclusion edits", async () => {
    const { gateway, event, fetcher } = await backend({ missingAssets: true });
    const snapshot = await gateway.get(event.id);
    await expect(
      gateway.review(event.id, 1, snapshot.content, {
        ...snapshot.facts,
        diet: { ...snapshot.facts.diet, detail: "Vegan" },
      }),
    ).rejects.toThrow(/cannot be saved/);
    await gateway.review(event.id, 1, snapshot.content, snapshot.facts);
    await expect(
      gateway.publish(event.id, 1, "publish", "key", "go-mail"),
    ).rejects.toThrow(/both current assets/);
    expect(fetcher.mock.calls.some(([url]) => url.endsWith("/approvals"))).toBe(
      false,
    );
  });
  it("rejects cross-event review material", async () => {
    const { gateway, event, fetcher } = await backend();
    const original = fetcher.getMockImplementation()!;
    fetcher.mockImplementation(async (url, options) =>
      url.endsWith("/review") && (options?.method ?? "GET") === "GET"
        ? new Response(
            JSON.stringify({
              event,
              generated_content: [{ event_id: "another-event" }],
              artifacts: [],
              inclusion_facts: [],
            }),
          )
        : original(url, options),
    );
    await expect(gateway.get(event.id)).rejects.toThrow(/another event/);
  });
});

it("never retries an approval write whose outcome is unknown, even with a new caller key", async () => {
  const { gateway, event, fetcher } = await backend();
  const snapshot = await gateway.get(event.id);
  await gateway.review(event.id, 1, snapshot.content, snapshot.facts);
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (url, options) =>
    url.endsWith("/approvals")
      ? Promise.reject(new Error("connection lost"))
      : original(url, options),
  );
  await expect(
    gateway.publish(event.id, 1, "publish", "try-1", "go-mail"),
  ).rejects.toThrow(/Do not create another/);
  await expect(
    gateway.publish(event.id, 1, "publish", "try-2", "go-mail"),
  ).rejects.toThrow(/Do not create another/);
  expect(
    fetcher.mock.calls.filter(([url]) => url.endsWith("/approvals")),
  ).toHaveLength(1);
});

it("refuses approval if the organizer's preview content ID is no longer current", async () => {
  const { gateway, event, fetcher } = await backend();
  const snapshot = await gateway.get(event.id);
  await gateway.review(event.id, 1, snapshot.content, snapshot.facts);
  await expect(
    gateway.publish(event.id, 1, "publish", "key", "outdated-mail-id"),
  ).rejects.toThrow(/changed since your preview/);
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/approvals"))).toBe(
    false,
  );
});

it("marks missing RSVP data unavailable and propagates unauthorized reads", async () => {
  const { gateway, event, fetcher } = await backend();
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (url, options) =>
    url.endsWith("/rsvps")
      ? new Response("{}", { status: 503 })
      : original(url, options),
  );
  const snapshot = await gateway.get(event.id);
  expect(snapshot.live?.rsvpsAvailable).toBe(false);
  expect(snapshot.live?.warnings.join(" ")).toContain(
    "Guest responses could not be loaded",
  );
  fetcher.mockImplementation(async (url, options) =>
    url.endsWith("/operations")
      ? new Response("{}", { status: 401 })
      : original(url, options),
  );
  await expect(gateway.get(event.id)).rejects.toMatchObject({
    code: "unauthenticated",
  });
});
