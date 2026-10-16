import { describe, expect, it } from "vitest";
import { parseWorkspace } from "./api";
import { contentDefinitions, routeContent } from "./content";
import { createPreviewGateway } from "./preview";

describe("structured Go output placement", () => {
  it("routes every Go tool kind by schema regardless of prose keywords or arrival order", async () => {
    const snapshot = await createPreviewGateway().get("preview-gathering");
    const kinds = [
      "invitation",
      "flyer_copy",
      "summary",
      "description",
      "document",
      "flyer_alt_text",
      "change_notice",
      "notion_note",
      "flyer_brief",
    ];
    // Synthetic tool-output fixtures. These do not test natural-language understanding in Go.
    const content = kinds.map((kind, index) => ({
      id: `result-${index}`,
      kind,
      body: "Location: blue; email: garden; flyer: Saturday. These words must not control placement.",
      subject: kind === "invitation" ? "A picnic for our neighbors" : null,
      producer: "superhuman_go",
      state: "needs_review",
      event_revision: 2,
    }));
    const parsed = parseWorkspace({ ...snapshot, content });
    const groups = routeContent(parsed.content);
    expect(groups.details.map((c) => c.kind)).toEqual(["description"]);
    expect(groups.design.map((c) => c.kind)).toEqual([
      "flyer_copy",
      "flyer_alt_text",
      "flyer_brief",
    ]);
    expect(groups.inclusion.map((c) => c.kind)).toEqual([
      "plain_language_summary",
    ]);
    expect(groups.documents.map((c) => c.kind)).toEqual([
      "event_document",
      "notion_note",
    ]);
    expect(groups.distribution.map((c) => c.kind)).toEqual([
      "invitation",
      "change_notice",
    ]);
    expect(groups.distribution[0].subject).toBe("A picnic for our neighbors");
    expect(parsed.event.location).toBe(snapshot.event.location);
    expect(Object.values(groups).flat()).toHaveLength(content.length);
    expect(
      Object.values(routeContent([...parsed.content].reverse()))
        .flat()
        .map((c) => c.id)
        .sort(),
    ).toEqual(parsed.content.map((c) => c.id).sort());
  });
  it("preserves distinct current and stale outputs without flattening by display label", async () => {
    const snapshot = await createPreviewGateway().get("preview-gathering");
    const old = {
      ...snapshot.content[0],
      id: "old-description",
      event_revision: 1,
    };
    const parsed = parseWorkspace({
      ...snapshot,
      content: [old, snapshot.content[0]],
    });
    expect(
      routeContent(parsed.content).details.map((c) => c.event_revision),
    ).toEqual([1, 2]);
  });
  it("fails visibly on unsupported kinds, duplicate IDs and malformed subjects instead of losing data", async () => {
    const snapshot = await createPreviewGateway().get("preview-gathering");
    expect(() =>
      parseWorkspace({
        ...snapshot,
        content: [{ ...snapshot.content[0], kind: "other_prose" }],
      }),
    ).toThrow(/Unsupported Go content kind/);
    expect(() =>
      parseWorkspace({
        ...snapshot,
        content: [snapshot.content[0], snapshot.content[0]],
      }),
    ).toThrow(/contract/);
    expect(() =>
      parseWorkspace({
        ...snapshot,
        content: [{ ...snapshot.content[0], subject: { text: "wrong type" } }],
      }),
    ).toThrow(/contract/);
    expect(Object.keys(contentDefinitions)).toHaveLength(9);
  });
});

describe("Member 4 artifact metadata mapping", () => {
  it("places hash-based Canva PNG and event-document exports without inventing preview URLs", async () => {
    const snapshot = await createPreviewGateway().get("preview-gathering");
    const metadata = {
      event_id: snapshot.event.id,
      event_revision: 2,
      sha256: "a".repeat(64),
      review_state: "needs_review",
      content_type: "image/png",
      byte_length: 123,
      canva_design_id: "synthetic-design",
    };
    const parsed = parseWorkspace({
      ...snapshot,
      assets: [
        { ...metadata, kind: "flyer_png" },
        {
          ...metadata,
          kind: "event_document",
          sha256: "b".repeat(64),
          content_type: "text/html",
          review_state: "reviewed",
        },
      ],
    });
    expect(parsed.assets.map((asset) => asset.kind)).toEqual([
      "flyer",
      "document",
    ]);
    expect(parsed.assets.map((asset) => asset.state)).toEqual([
      "needs_review",
      "ready",
    ]);
    expect(parsed.assets[0].preview_url).toBeUndefined();
    expect(parsed.assets[0].id).not.toBe("synthetic-design");
    expect(() =>
      parseWorkspace({
        ...snapshot,
        assets: [{ ...metadata, kind: "flyer_png", event_id: "another-event" }],
      }),
    ).toThrow(/this event/);
  });
});
