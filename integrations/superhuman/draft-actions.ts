import * as sdk from "@codahq/packs-sdk";

// This adapter changes only the Go approval UI. Every write still goes through
// the existing authenticated canonical MCP tool; never use it to send/publish.
export async function callDraftTool(
  context: Pick<sdk.ExecutionContext, "fetcher">,
  endpoint: string,
  name: "create_event" | "update_event" | "save_generated_content",
  args: Record<string, unknown>,
): Promise<string> {
  const response = await context.fetcher.fetch({
    method: "POST",
    url: endpoint,
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
  });
  const result = response.body?.result;
  if (response.body?.error || !result || result.isError) {
    throw new sdk.UserVisibleError("The draft was not confirmed saved. Read the event again before retrying; reuse the same creation idempotency key.");
  }
  return JSON.stringify(result.structuredContent ?? result.content);
}

export function registerDraftActions(pack: sdk.PackDefinitionBuilder, endpoint: string) {
  const text = (name: string, description: string) => sdk.makeParameter({ type: sdk.ParameterType.String, name, description });
  pack.addFormula({
    name: "CreateDraftEvent",
    description: "Create one organizer-confirmed draft via the website MCP. No guests or external writes. Use this typed action if MCP create_event approval cannot display. First list_events to avoid duplicates. Reuse the SAME requestKey on retry. Confirm details first.",
    isAction: true,
    resultType: sdk.ValueType.String,
    parameters: [
      text("requestKey", "Unique idempotency key; reuse exactly on retry."),
      text("title", "Confirmed event title."),
      text("startsAt", "ISO datetime with UTC offset, for example 2026-11-12T15:00:00-08:00."),
      text("endsAt", "ISO datetime with UTC offset."),
      text("timezone", "Confirmed IANA timezone."),
      text("location", "Confirmed location; empty if unknown."),
      text("description", "Organizer-reviewed event description, written by Go."),
    ],
    execute: async function ([requestKey, title, startsAt, endsAt, timezone, location, description], context) {
      return callDraftTool(context, endpoint, "create_event", { idempotency_key: requestKey, title, starts_at: startsAt, ends_at: endsAt, timezone, location, description });
    },
  });
  pack.addFormula({
    name: "UpdateDraftLocation",
    description: "Change only the location of an organizer-confirmed event through website MCP. Preserves event ID, requires current revision, sends/publishes nothing. Confirm the location first.",
    isAction: true,
    resultType: sdk.ValueType.String,
    parameters: [text("eventId", "Saved event ID."), sdk.makeParameter({ type: sdk.ParameterType.Number, name: "revision", description: "Current expected revision from list_events/get_event." }), text("location", "Confirmed new location.")],
    execute: async function ([eventId, revision, location], context) {
      return callDraftTool(context, endpoint, "update_event", { event_id: eventId, expected_revision: revision, location });
    },
  });
  pack.addFormula({
    name: "SaveDraftContent",
    description: "Save Go-written description, plain_language_summary, invitation draft or flyer_brief for organizer review through website MCP. This never generates a Canva design or sends/publishes anything.",
    isAction: true,
    resultType: sdk.ValueType.String,
    parameters: [text("eventId", "Saved event ID."), sdk.makeParameter({ type: sdk.ParameterType.Number, name: "revision", description: "Current event revision." }), text("kind", "One of description, plain_language_summary, invitation, flyer_brief."), text("body", "Go-written draft text."), text("subject", "Invitation subject; empty string for other kinds.")],
    execute: async function ([eventId, revision, kind, body, subject], context) {
      if (!["description", "plain_language_summary", "invitation", "flyer_brief"].includes(kind)) throw new sdk.UserVisibleError("Unsupported draft content kind.");
      return callDraftTool(context, endpoint, "save_generated_content", { event_id: eventId, expected_revision: revision, kind, body, ...(subject ? { subject } : {}) });
    },
  });
}
