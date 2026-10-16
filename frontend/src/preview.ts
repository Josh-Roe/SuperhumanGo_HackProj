// Synthetic UI fixtures only. Never persisted, sent, or presented as live Go/provider evidence.
import type {
  Content,
  EventGateway,
  EventInput,
  WorkspaceEvent,
} from "./types";
import { emptyFacts } from "./types";
export function createPreviewGateway(): EventGateway {
  const copy = <T>(value: T): T => structuredClone(value);
  const content = (kind: Content["kind"], body: string): Content => ({
    id: kind,
    kind,
    body,
    producer: "superhuman_go",
    event_revision: 2,
    state: "needs_review",
  });
  const seed: WorkspaceEvent = {
    event: {
      id: "preview-gathering",
      revision: 2,
      title: "A neighborhood, together",
      description: "",
      location: "Community garden · venue to confirm",
      starts_at: "2026-11-07T18:00:00Z",
      ends_at: "2026-11-07T20:00:00Z",
      timezone: "America/Los_Angeles",
      organizer_contact: "organizer@example.com",
      links: [],
      invitees: [{ id: "example-1", email: "guest@example.com" }],
      status: "draft",
      created_via: "superhuman_go",
    },
    content: [
      content(
        "description",
        "Join your neighbors for a relaxed afternoon in the community garden. Meet new people, share ideas, and help shape our next gathering.",
      ),
      content(
        "plain_language_summary",
        "Meet your neighbors at the community garden. We will talk and share ideas. Venue access and food options still need confirmation.",
      ),
      content(
        "invitation",
        "Hello neighbors,\n\nYou’re invited to our community gathering. Please review the current event details before you travel. Reply to let us know if you can join.\n\nWe hope to see you there!",
      ),
      content(
        "flyer_brief",
        "A welcoming community-garden flyer. Use a soft green palette, clear high-contrast type, and a simple botanical layout. Keep the date and location prominent.",
      ),
      content(
        "event_document",
        "Community gathering\n\nMeet your neighbors and share ideas for the neighborhood.\n\nVenue and access details are awaiting organizer confirmation.",
      ),
    ],
    work: [{ id: "sample-work", event_revision: 2, state: "needs_review" }],
    assets: [],
    facts: emptyFacts(),
    findings: [],
    operations: [
      {
        id: "sample-calendar",
        provider: "Calendar",
        kind: "calendar_upsert",
        event_revision: 1,
        state: "succeeded",
        receipt: "Synthetic receipt · previous revision",
      },
      {
        id: "sample-gmail",
        provider: "Gmail",
        kind: "gmail_draft",
        event_revision: 1,
        state: "failed",
        error_code: "integration_not_connected",
      },
    ],
    rsvps: [
      {
        invitee_id: "example-1",
        status: "needs_review",
        source: "email",
        source_id: "synthetic-reply",
        observed_at: "2026-10-16T16:00:00Z",
        event_revision: 1,
        conflict: true,
      },
    ],
    gmail: { sent: false, event_revision: 1, draft_id: "synthetic-draft" },
    review_revision: null,
  };
  const records = new Map([[seed.event.id, seed]]);
  function current(id: string, revision?: number) {
    const item = records.get(id);
    if (!item) throw new Error("Event not found. Refresh the dashboard.");
    if (revision !== undefined && item.event.revision !== revision)
      throw new Error(
        "revision_conflict: Go or another session changed this event. Reload the current revision before saving.",
      );
    return item;
  }
  return {
    mode: "preview",
    async list() {
      return copy([...records.values()].map((item) => item.event));
    },
    async get(id) {
      return copy(current(id));
    },
    async save(id, input: EventInput, revision) {
      if (id) {
        const item = current(id, revision);
        item.event = {
          ...copy(input),
          id,
          revision: item.event.revision + 1,
          status: item.event.status,
          created_via: item.event.created_via,
        };
        item.review_revision = null;
        item.work = [
          {
            id: crypto.randomUUID(),
            event_revision: item.event.revision,
            state: "awaiting_go",
          },
        ];
        return copy(item);
      }
      const newId = crypto.randomUUID();
      const item: WorkspaceEvent = {
        event: {
          ...copy(input),
          id: newId,
          revision: 1,
          status: "draft",
          created_via: "manual",
        },
        content: [],
        work: [],
        assets: [],
        facts: emptyFacts(),
        findings: [],
        operations: [],
        rsvps: [],
        gmail: null,
        review_revision: null,
      };
      records.set(newId, item);
      return copy(item);
    },
    async prepare(id, revision) {
      const item = current(id, revision);
      if (
        !item.work.some(
          (work) =>
            work.event_revision === revision &&
            ["awaiting_go", "running"].includes(work.state),
        )
      )
        item.work.push({
          id: crypto.randomUUID(),
          event_revision: revision,
          state: "awaiting_go",
        });
      return copy(item);
    },
    async review(id, revision, content, facts) {
      const item = current(id, revision);
      item.content = copy(content);
      item.facts = copy(facts);
      item.review_revision = revision;
      return copy(item);
    },
    async publish() {
      throw new Error(
        "Local preview cannot publish or synchronize providers. Connect the agreed API and review a live event first.",
      );
    },
  };
}
