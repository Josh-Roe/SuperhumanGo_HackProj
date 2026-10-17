# Shared product context: event organizer website

Updated 2026-10-16, America/Los_Angeles. **Website name: undecided.** This file owns the agreed brief; personal progress and handoffs live in four separate files. During implementation, Member 2 is its sole editor.

## Read every context before work

Every agent must read [AGENTS.md](AGENTS.md), this file, and **all four** contexts before starting, taking a handoff, changing a contract, or finishing:

- [01 Frontend](docs/contexts/01_FRONTEND.md)
- [02 Backend/Supabase](docs/contexts/02_BACKEND_SUPABASE.md)
- [03 Superhuman Go/Google](docs/contexts/03_GO_GOOGLE.md)
- [04 Canva/inclusion/presentation](docs/contexts/04_CANVA_INCLUSION.md)

Write only your own personal context. Propose cross-team changes there for the relevant owner. Fetch/read new versions across devices; Git does not inject updates into existing agent chats automatically. [Tasks and prompts](docs/TEAM_TASKS.md) define ownership; [the integration contract](docs/INTEGRATION_CONTRACT.md) defines the initial handoff interfaces.

## Accepted product decision

The team lead has selected an event organizer website. Organizers create an event once, use **Superhuman Go (with its built-in Grammarly writing assistance)** to prepare clear material, review design/inclusion, distribute invitations, and propagate approved changes across Gmail, Google Calendar, Canva, and stored event material. Productivity is the working primary-track recommendation; inclusion is a core capability. Confirm the final Devpost track with the team lead.

The distinctive demo is a real change of time/location causing a visible, versioned update across Calendar, Gmail, and Canva. Keep the latest event accessible through one stable link while clearly identifying older snapshots.

**User decision, 2026-10-16 — guided Go pipeline:** one Go conversation walks the organizer through details → writing → review → inclusion → optional flyer → send → RSVPs (`event_progress`, `approve_draft`, `save_inclusion_facts`, `send_invitations`). Approval may happen in the Go chat: the organizer's explicit "send" plus Go's per-call confirmation records the same exact-content approval (`organizer_approve`) and runs the same idempotent distribution. Website approval stays available; the website shows pipeline progress. Flyer preview approval remains a website action.

**Agreed workflow update, 2026-10-16:** the organizer primarily prompts Superhuman Go. Go connects to the website's custom authenticated MCP server, creates/edits canonical tasks/events, prepares writing and coordinates approved provider work, then records IDs/revisions/results for the website to display. Manual website creation/editing remains available. This follows the team lead's Member 2 instruction and the matching Member 1/4 context handoffs. Connecting MCP does not itself prove an automatic website-to-Go trigger or authorize publication. A separate standalone-task schema and the frontend wire mapping are published as implementation proposals in Member 2's context pending consumer agreement.

## Organizer flow

1. **Log in:** Supabase Auth; connect the organizer's Gmail/Calendar/Canva accounts as supported by their real integrations.
2. **Event details:** title, description, location/online link, start/end with timezone, relevant links, invitee email addresses, organizer contact, and venue/diet/accessibility facts.
3. **Design and inclusion:** manually create/edit a Canva flyer or request AI assistance; prepare an event document; review plain-language writing and inclusion findings before distribution.
4. **Distribution:** preview the Go-written invitation and event material. Publish the reviewed version to Calendar attendees and Gmail. Email includes the Calendar event/invitation link, current details/document links, and the flyer as appropriate. Store document/flyer artifacts in Supabase Storage.
5. **Changes:** save a new canonical event revision; regenerate prose through Go; update the same Calendar event and Canva design or its new version/export. Replace an unsent Gmail draft. If its invitation was sent, create a new change-notification email, retaining the sent history. Send via the organizer's authorized update flow.

## Recipient flow

- Receive the published email and Calendar invitation; use Calendar/email/flyer/current event page to learn the details and contact the organizer.
- Calendar updates target the original event ID. A changed event produces a new notification email when the earlier email was already sent. Original delivered attachments cannot change; new exports and a stable current link handle freshness.
- RSVP through Calendar and/or an email reply classified by Go as attending/maybe/not attending. Match the invited sender and event; ambiguous replies require review. Optional Forms collect extra RSVP/diet/accessibility information after the core flow works.

## Inclusion scope

- Plain-language summary and actionable event instructions.
- Organizer-confirmed step-free entrance/ramp and elevator facts.
- Dietary accommodations and private collection of restrictions where required.
- Potential conflicts with significant religious observances, checked automatically against Google's public Christian, Jewish, Muslim, Hindu and Orthodox Christian holiday calendars in the event's timezone. All five are checked by default; the organizer can narrow them or add sourced observances. Never infer religion from ethnicity/name.
- Captioning availability and clear loud-sound/strobe notices.
- Parking, restrooms, and Google Forms are stretch features from the team brief. Unknown accommodations remain unknown; do not invent guarantees.

## Superhuman Go is central

Go is responsible for event descriptions, plain-language summaries, invitations, change summaries, event-document prose, and RSVP interpretation. Grammarly writing assistance is part of Superhuman Go; it is not integrated separately. The website requests and displays generation work; Python supplies durable state and reliable tool execution.

Supported starting architecture: **Go → authenticated hosted MCP tools → Python → Supabase/provider operations**. The website may enqueue work for Go. Member 3 must verify a supported account-side trigger before promising automatic website-to-Go execution; a manual Go command or verified schedule is the explicit MVP fallback, displayed as awaiting Go rather than fake completion. No general Go inference endpoint has been established. See [official MCP guidance](https://coda.io/packs/build/latest/guides/blocks/mcp/) and [agent builder](https://support.grammarly.com/hc/en-us/articles/47453002811021-Create-and-configure-agents-with-the-agent-builder).

Gmail/Calendar writes may use Go's verified native connectors or backend OAuth tools called by Go. Member 3 chooses **one writer per provider operation**, records its IDs/results, and prevents duplicated native-connector plus API execution. No secrets are passed as model prose. Each organizer's access must be enforced at the tool boundary.

Gemini is not used; all generated prose comes from Go. A live Go operation and returned provider receipt must appear in the final demo.

## Stack and synchronization plan

- React/TypeScript TSX website; Python FastAPI on the prepared VPS/container path.
- Supabase Auth, Postgres as canonical event state, and Storage for event documents/flyer exports. Enforce owner-scoped authorization/RLS and private RSVP/credential storage.
- Canonical event revisions, an operation/outbox queue, stable provider IDs, and read-back receipts keep changes traceable. Use idempotency by event/revision/operation/recipient where relevant, optimistic concurrency, retries, and per-provider stale/error states.
- OAuth/API credentials and service-role secrets remain server-side. Supabase publishable keys may be in the browser only with appropriate RLS.
- Custom training, C++ model serving, and extra integrations are deferred until the required event/Go loop works. The existing ONNX scaffold remains optional.

## Decision continuity

- Earlier React/Python, GitHub/Live Share, and supported Go MCP choices remain in effect.
- The previous three-agent split is **superseded** by the team lead's four-member request, 2026-10-16. Single-file progress editing is superseded by the four owner-specific contexts; only global agreed requirements remain here.
- Earlier brainstorming ideas are not the product specification. This event-management brief is the approved direction.
- Notion is out of scope. Forms/parking/restrooms are explicit stretch scope. Final sequencing can change by team decision.

## Current evidence and blockers

The initial handoff contained a tested React/Python/MCP scaffold, optional ONNX boundaries, and Docker/Caddy deployment files. Implementation now exists on member branches; the Member 2 integration branch combines the frontend preview, Go/Google workflows, Canva/inclusion services, and Supabase repositories/migrations. See each owner's context for actual evidence. Supabase SQL/RLS checks and local tests pass; router/MCP registration, frontend live wire mapping, account grants, and the complete provider demo remain pending. Planning documents alone are not live integration evidence.

Historical evidence: scaffold revision `78d5477` passed [Linux CI and Docker smoke testing](https://github.com/Josh-Roe/SuperhumanGo_HackProj/actions/runs/38876793067). Local scaffold validation reported 37 backend and 3 frontend tests; optional ML behavior differs from base CI. This is not evidence that planned event features work.

Unresolved external setup: Supabase project/credentials, organizer account connections, Canva eligible account/template fields, hosted HTTPS domain, Go installation and activation mode, four human names/usernames, and final Devpost track. Record each resolved item in its owner's context with evidence, never with secret values.

## Immediate handoff

Send each member their [copy-ready prompt](docs/TEAM_TASKS.md). First coordinate the v0 contracts, then demonstrate Go reading an authorized test event and saving generated output before expanding provider automation. Preserve [hackathon preparation/disclosure rules](docs/HACKATHON.md). No event feature work or external sends were performed by this documentation preparation.
