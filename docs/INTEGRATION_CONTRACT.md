# Initial event integration contract

Owner: Member 2. Status: **planning baseline, not implemented API**. Members 1/3/4 read this and propose adjustments in their own contexts; agree changes before relying on them. Existing `/api/health`, `/api/status`, and MCP scaffold behavior must stay functional during integration.

**Agreed product/interface additions, 2026-10-16:** the team lead's Go-first workflow retains manual editing and requires authorized create/update task/event MCP tools over the same canonical repository. Member 3 owns their registration. Go creation is separate from organizer publish approval. Members 3/4 proposed matching asset-prose kinds below; Member 2 accepts and implements those names and their supplied repository/Storage ports. The exact standalone-task and REST wire schemas are exported from `hackathon_backend.api.schema` and recorded in [Member 2's context](contexts/02_BACKEND_SUPABASE.md); the frontend's different proposed `WorkspaceEvent` wire model is **not yet agreed or enabled**. This document does not imply those factories are registered in the running scaffold.

**Guided pipeline (user decision 2026-10-16):** MCP `event_progress(event_id)` → `{event_id, revision, title, mode: first_send|update, stages: [{stage, status: done|todo|optional|blocked, detail}], next_stage}` over stages details, writing, review, inclusion, flyer, send, rsvps. `approve_draft(content_id, expected_revision, subject?, body?)` marks the send draft `ready` (edits saved as `producer: organizer`). `save_inclusion_facts(event_id, …yes|no|unknown, diet_options?)` merges organizer answers (unknown unsourced). `send_invitations(event_id, expected_revision)` records an `organizer_approve` approval for the current send content and runs distribution; a retry for a sent revision replays it. REST mirror: `GET /api/events/{id}/progress` (same shape).

## Canonical records

| Record | Initial fields and invariants |
| --- | --- |
| Event | `id`, authenticated `owner_id`, integer `revision`, `title`, `description`, `location`, `starts_at`, `ends_at`, IANA `timezone`, `links[]`, `organizer_contact`, `status`, timestamps; end is after start |
| Invitee | `id`, `event_id`, normalized `email`, `display_name?`; RSVP and sensitive needs are private |
| Inclusion facts | `event_id`, `revision`, step-free entrance, elevator, captions, diet options, loud sound/strobe information; facts use `yes/no/unknown`, source/confirmed-by and date where appropriate |
| Generated content | `event_id`, `event_revision`, `kind`, `body`, `producer`, `state`, timestamp; kinds include description, summary, invitation, change notice, document; producer is `superhuman_go` or `organizer` (organizer edit of Go output) |
| Artifact | `event_id`, `event_revision`, `kind`, Storage path, provider design/document ID, exported-version ID/hash, current URL/access policy; no mixed-revision distribution |
| Provider binding | event + provider + account/target + remote ID; store Calendar event ID, Gmail draft/message/thread IDs and sent state, Canva design ID and export revision |
| Operation | `id`, event/revision, kind, idempotency key, authorization/approval reference, state, attempts, error code, provider receipt; durable queue/outbox |
| RSVP | invitee/event, `attending/maybe/not_attending/no_response/needs_review`, source, source message/Calendar ID, observed time, event revision; preserve provenance rather than silently overwriting conflicts |

`owner_id` is taken from validated identity, never trusted from request JSON. OAuth tokens must be encrypted/server-held and scoped to the correct account. Schema/migrations/RLS are Member 2's responsibility; 3/4 use repository interfaces and request additions.

The agreed Go asset-prose kinds are `flyer_brief`, `flyer_copy`, `event_document`, `plain_language_summary`, and `flyer_alt_text`, in addition to the original kinds. `producer=superhuman_go` is asserted only through the authenticated server workflow; browser edits retain `producer=organizer`. A producer label does not establish a real Go run without execution evidence. See Members 3/4's concrete adapters and [the Storage/registration handoff](../supabase/README.md).

## REST surface to agree first

Proposed `/api/events` create/list; `/api/events/{id}` read/update with expected revision; `/api/events/{id}/prepare` queue Go/content work; `/api/events/{id}/review` inspect material/inclusion; `/api/events/{id}/publish` execute a reviewed plan; `/api/events/{id}/sync` request approved update/retry; `/api/events/{id}/operations` inspect status; `/api/events/{id}/rsvps` list private organizer responses.

Use consistent typed errors: `unauthenticated`, `forbidden`, `revision_conflict`, `integration_not_connected`, `awaiting_go`, `needs_review`, `provider_failed`. Include operation ID for asynchronous work and server-known event revision; never return credential values. Member 2 publishes exact schemas/examples and Member 1 uses an adapter until those are agreed.

## Go/MCP handoff

Member 3 defines the final tool names/schemas. Initial capabilities: read an authorized event snapshot; list/claim pending event work; save Go-written content for an expected revision; request/read inclusion findings; request Canva generation/export; preview and execute an organizer-approved distribution/update plan; record actual provider receipts; record a matched RSVP classification. Tools with side effects must be annotated accordingly and enforce authorization themselves.

Go tools call Member 2's event/queue repositories and Member 4's inclusion/assets/Canva interfaces. Never read all organizers' jobs under one shared token or accept a caller-supplied owner ID as proof of authorization. Manual Go invocation is allowed as the labeled MVP fallback; fully automatic triggers are a separately verified capability.

## Module interfaces to agree during the first handoff

- Member 2 provides current principal/owner validation, immutable event snapshot, compare-and-set revision update, content/artifact save, job claim/receipt, storage-link creation, and credential-vault access interfaces.
- Member 3 provides Go workflow/Google provider operations and a registration point in `main.py`. Backend API routers and Member 4 routers are passed in; do not make others edit `main.py` concurrently.
- Member 4 provides `check_inclusion(event_snapshot)`, `prepare_flyer(event_snapshot, go_content, template_binding)`, `export_flyer(binding, revision)`, and `render_event_document(event_snapshot, go_content)` adapters. Names are proposed; agree concrete Python types before implementation. Generation/rendering uses Go-supplied prose, not a hidden replacement LLM.
- Member 1 consumes event/detail/review/operation/RSVP schemas and shows each artifact's revision plus an accessible text status. New writes carry expected revision and an explicit user action for publish/update.

## Lifecycle and update invariants

1. Save details and increment revision; queue preparation. A Go worker or manual session claims the authorized work. UI shows `awaiting_go` until a real output exists.
2. Review Go content, current Canva/document artifacts, and inclusion facts. Findings can be unresolved/unknown and require organizer acknowledgment. No premature invites while merely designing.
3. Publish the exact reviewed revision. Member 3 creates/reuses the Calendar event with attendees and obtains the actual event link, finalizes the Go-written Gmail draft with that link and current assets, then sends under the approved publish plan. Calendar invitations can precede Gmail completion; partial failure is visible and retryable without a second Calendar event.
4. Change details: new revision invalidates previous preparation. Regenerate Go prose and Canva exports. Update the existing Calendar event; preserve attendees/RSVPs and unrelated fields, use provider concurrency safeguards, and select `sendUpdates` deliberately.
5. If Gmail is unsent, replace its message within the draft. If sent, preserve sent message ID/history and prepare a new change-notification draft. A missing/deleted draft is not proof it was sent: reconcile provider state. Read back results and store provider receipts before declaring success.
6. Two notifications may be intentional (Calendar update and explanatory Gmail email), but retries of either operation must not duplicate it. Sending policy and per-recipient privacy are explicit; avoid exposing all invitee addresses in a bulk `To` field by default.

State vocabulary: `queued`, `awaiting_go`, `running`, `needs_review`, `ready`, `succeeded`, `failed`, `superseded`. Event phase and individual operation state are separate. A newer event revision supersedes stale generated outputs and jobs.

## External behavior and sources

- [Superhuman hosted MCP](https://coda.io/packs/build/latest/guides/blocks/mcp/) and [agent setup/triggers](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder): validate available account capabilities first.
- [Gmail draft lifecycle](https://developers.google.com/workspace/gmail/api/guides/drafts): draft IDs and underlying message IDs have different lifecycles; sent mail creates a new message.
- [Calendar updates](https://developers.google.com/workspace/calendar/api/v3/reference/events/update): preserve remote event ID and handle notifications/concurrency; an invite does not guarantee automatic appearance on every recipient's calendar because recipient settings differ.
- [Canva autofill](https://www.canva.dev/docs/apps/mcp/tools/autofill-design/): check account eligibility and template/design dataset fields. Test update-in-place vs new design/export; never assume arbitrary existing flyer text is programmatically editable.
- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security): enforce ownership and keep privileged credentials off the browser. Do not expose private RSVP/needs data through public event links.
