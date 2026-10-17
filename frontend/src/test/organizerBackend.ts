import { vi } from "vitest";
import { createOrganizerGateway } from "../live";
import { createPreviewGateway } from "../preview";

export async function backend({ missingAssets = false } = {}) {
  const snapshot = await createPreviewGateway().get("preview-gathering");
  let event = {
    ...snapshot.event,
    id: "00000000-0000-4000-8000-000000000001",
    revision: 1,
    invitees: [
      { id: "guest-id", email: "guest@example.com", display_name: "Guest" },
    ],
  };
  let content = [
    {
      id: "go-mail",
      event_id: event.id,
      event_revision: 1,
      kind: "invitation",
      body: "Go wrote this invite",
      subject: "Join us",
      producer: "superhuman_go",
      state: "needs_review",
      created_at: "2026-10-16T00:00:00Z",
    },
  ];
  const metadata = (kind: string) => ({
    event_id: event.id,
    event_revision: event.revision,
    kind,
    sha256: "a".repeat(64),
    review_state: "reviewed",
  });
  const fetcher = vi
    .fn()
    .mockImplementation(async (url: string, options: RequestInit = {}) => {
      const method = options.method ?? "GET";
      const json = (value: unknown, status = 200) =>
        new Response(JSON.stringify(value), { status });
      const body = options.body ? JSON.parse(String(options.body)) : undefined;
      if (url.startsWith("/api/events?")) return json([event]);
      if (url === `/api/events/${event.id}`) {
        if (method === "PUT") {
          event = {
            ...event,
            ...body,
            revision: event.revision + 1,
            invitees: body.invitees.map((person: object) => ({
              ...person,
              id: "server-id",
            })),
          };
          return json(event);
        }
        return json(event);
      }
      if (url.endsWith("/review") && method === "GET")
        return json({
          event,
          generated_content: content,
          artifacts: missingAssets
            ? []
            : ["flyer_png", "event_document"].map((kind) => ({
                id: kind,
                ...metadata(kind),
                data: metadata(kind),
                is_current: true,
              })),
          inclusion_facts: [],
        });
      if (url === "/api/content/go-mail/review") {
        content = [
          {
            ...content[0],
            ...body,
            id: body.body ? "organizer-mail" : "go-mail",
            producer: body.body ? "organizer" : "superhuman_go",
            state: "ready",
          },
        ];
        return json(content[0]);
      }
      if (url.endsWith("/prepare"))
        return json(
          {
            id: "job-id",
            event_id: event.id,
            event_revision: event.revision,
            state: "awaiting_go",
          },
          202,
        );
      if (url.endsWith("/inclusion") && method === "GET")
        return json({
          event_id: event.id,
          version: 0,
          saved_at_event_revision: null,
          updated_at: null,
          facts: {},
          review: {
            event_id: event.id,
            event_revision: event.revision,
            audience: "organizer_private",
            requires_review: true,
            certification: false,
            findings: [
              {
                category: "religious_observances",
                status: "attention",
                reason: "overlap_with_observance",
                sources: [
                  {
                    label: "Google Calendar public holidays: Jewish Holidays",
                    observed_at: "2026-10-16T00:00:00Z",
                    confirmed_by: "Google Calendar public holiday feed",
                    url: null,
                  },
                ],
                conflicts: ["Yom Kippur"],
                go_generation_id: null,
              },
            ],
          },
        });
      if (url.endsWith("/operations")) return json([]);
      if (url.endsWith("/rsvps"))
        return json([
          {
            event_id: event.id,
            invitee_id: "guest-id",
            event_revision: event.revision,
            status: "attending",
            source: "calendar",
            source_id: "remote-event",
            observed_at: "2026-10-16T00:00:00Z",
            private_note: "DO NOT DISPLAY",
          },
        ]);
      if (url.endsWith("/current")) {
        if (missingAssets) return json({}, 404);
        const kind = url.includes("flyer_png") ? "flyer_png" : "event_document";
        return json({
          ...metadata(kind),
          url: `https://storage.example/${kind}?token=synthetic`,
        });
      }
      if (url.endsWith("/approvals"))
        return json({
          id: "approval-id",
          event_id: event.id,
          event_revision: event.revision,
          action: body.action,
          invitation_content_id: body.invitation_content_id,
        });
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
  vi.stubGlobal("fetch", fetcher);
  return {
    gateway: createOrganizerGateway("organizer-session"),
    event,
    fetcher,
  };
}
