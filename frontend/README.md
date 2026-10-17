# Event workspace · Member 1

The site opens directly to **Your events**. The sidebar has Your events, Settings, and Profile. The plus button first prompts the user to open standalone Superhuman Go. It creates no placeholder event. After Go saves the event, return and check Your events. Manual entry is a secondary option; existing events retain details → design/inclusion → distribution. Signup/login is skipped at the user's request.

```sh
npm ci
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
npm run lint
npm test
npm run build
```

Share Vite's Network URL with teammates on the same Wi-Fi. Keep the host awake and the process running. The current workspace is an explicitly labeled **local preview**: sample data and profile edits exist only in each browser tab. Reload resets them. It cannot publish or send invitations. No account authentication or private backend access is bypassed.

## Superhuman Go handoff

Settings and the design step open [Superhuman Go](https://go.superhuman.com/) in another tab. The organizer adds the team's custom MCP connector in Go and authorizes its tools. They then prompt Go to save event details, Canva artifacts, prose, and distribution preparation into the canonical website records. Return to the event and refresh to review actual results once integration is connected.

Set `VITE_PUBLIC_MCP_URL` to the public hosted HTTPS connector address supplied by Member 3. Without it, the UI clearly says setup is pending. No localhost URL, auth token, fabricated install deep link, or automatic connection success is substituted. The UI supplies a copyable event-ID/revision prompt, with a manual-copy fallback on HTTP LAN pages where Clipboard access is unavailable. Opening Go does not transmit the prompt or install anything automatically. See [official connector help](https://support.grammarly.com/hc/en-us/articles/40642362241293-About-Superhuman-Go-agents-and-connectors).

The Go handoff is implemented; the actual custom MCP and backend/provider round trip still belong to Members 2–4. Current sample events do not synchronize with Go. Canva/Gmail/Calendar connection rows are labeled unverified. Organizer review and send confirmation remain required.

## Integration boundary

`src/types.ts` defines the UI review model and `src/api.ts` validates incoming records. The connected test uses Member 2's published canonical read API. The obsolete proposed write adapter has been removed: production editing/review/publishing remain disabled until the actual backend endpoints are mapped. The local preview retains the manual flow. Member 3's `/api/dev` shape is not production Supabase data. Ownership, revisions, review and idempotency must be enforced server-side.

Canva previews render actual HTTPS metadata when supplied. Unknown inclusion facts remain unknown; sourced yes/no facts require confirmation dates. Access/sensory details and prose previews are collapsed to keep the main flow small. Provider status and private guest responses are expandable sections inside distribution. Sent email/attachments remain immutable; sent invitations require a new change notice, while unsent drafts are replaced. Exact Canva transaction digest approval and public event links remain pending backend handoffs.

Checks cover direct entry, the three sidebar links/stages, event creation, Go links/prompts/setup-pending states, writing provenance/review gates, inclusion sources, provider errors, private RSVP evidence, local profile editing, auth/REST boundary errors, revision conflicts, and timezone/DST conversion. Desktop/mobile browser and full screen-reader verification for this revision remain separate checks.

## Free-form requests in standalone Go

The intended pipeline is **user describes the event in Go → Go calls typed MCP tools → backend validates/stores canonical records → website renders the structured snapshot**. Users do not need headings, keywords, JSON, or a fixed order. Go asks about missing dates/timezones and ambiguous instructions before committing those facts. The website routes by explicit record fields and content kinds; words inside a body never overwrite event fields.

`src/content.ts` covers all current Member 3 content kinds. `summary` and `document` are normalized aliases; flyer brief/copy/alt text, email subjects, documents and optional Notion notes are preserved. Unsupported kinds and duplicate content IDs fail visibly instead of being discarded. `parseWorkspace` also normalizes Member 4's `flyer_png`/`event_document` and `review_state` metadata. Hash-derived artifact IDs are UI keys only; preview URLs are never invented. Different event IDs are rejected. Actual signed links and provider receipts must come from the authenticated server.

| Structured output                                                 | Website destination   |
| ----------------------------------------------------------------- | --------------------- |
| Canonical title, location, times, timezone, invitees              | Event details         |
| `description`                                                     | Event details writing |
| `flyer_brief`, `flyer_copy`, `flyer_alt_text`                     | Canva design          |
| `summary` / `plain_language_summary` and inclusion facts/findings | Inclusion             |
| `document` / `event_document`, `notion_note`                      | Documents             |
| `invitation`, `change_notice`, subject, Gmail/Calendar receipts   | Distribution          |

`App` accepts an `eventGateway` composition prop for an already-authenticated backend adapter; it defaults to the public local preview. Refresh loads list/detail snapshots from that gateway. This composition seam and mocked typed-output tests are not a live Go transfer or natural-language understanding test. The connected read-only test polls every ten seconds while visible and refreshes on window focus.

Canonical Supabase storage and organizer API factories now exist in main. Remaining work includes application registration, owner-scoped create/update event MCP tools, full review-material mapping and a standalone Go round trip. Member 3's current branch exposes read/queue/save-content tools, but not event create/update tools. See Member 1 context for the exact handoff.

## Current objective: verify a real Go-created event

Settings → **Test Go → website** → **Check event API** probes `/api/config` before requesting any account credentials. The current LAN baseline returns 404 because Member 2's router has not been registered in Member 3's composition. This is a visible setup blocker, not a successful Go connection.

The new `createEventTransferGateway` accepts Member 2's published canonical read contract: paginated `GET /api/events?limit=100&offset=N` returns `EventRecord[]`; `GET /api/events/{id}` returns `EventRecord`. It carries the organizer's Supabase Bearer token. Once API readiness is confirmed, an existing account can connect through Settings; its access token remains in memory, expires, and is cleared on disconnect. There is no initial signup gate. This narrow connection is read-only and loads event details only; design/distribution stages and writes are disabled so empty material arrays are not mistaken for real provider state. No speculative write adapter remains.

After deployment/registration, test with this synthetic Go request:

> Create a draft event named Go transfer test 01 on November 14, 2026, from 10 AM to noon in America/Los_Angeles, at Test Garden. Description: connection test. No guests yet. Save it through the Event Workspace connector and return its saved event ID and revision. Do not send invitations or create provider assets.

Connect the same organizer in Settings, choose New event → **Check Your events** (or refresh the list), and open that event. Compare the displayed saved ID, title, location, times/timezone, description and guests with Go's tool receipt. A matching name alone does not prove transfer. Changing a location should retain the ID and increment the revision. Reloading should read persisted state. Keep this first test limited to canonical details.

**Current blocker:** a Vercel project exists, but no reachable backend/Go connector has been verified. Member 3 still needs to register Member 2's router and add create/update event MCP tools. No live end-to-end proof can run until those are available. Mocked transfer tests do not prove standalone Go execution.


## Vercel setup and remaining owner actions

The main backend merge is incorporated into `codex/member-1-frontend`. Merge [PR #2](https://github.com/Josh-Roe/SuperhumanGo_HackProj/pull/2) to include this frontend in main.

1. **Member 3:** wire production Supabase/auth/event dependencies in `main.py`, include Member 2's API router before the MCP catch-all, and register authenticated event create/update MCP tools. Use the canonical service, ownership, expected revisions and idempotency; return saved ID/revision. Current read/content tools cannot create events.
2. **Backend deployment owner:** deploy Python to public HTTPS. Configure backend variables from root `.env.example`, an organizer test account and MCP authorization scoped to that owner. Set `APP_DOMAIN` to the public backend hostname. Keep service-role, encryption and OAuth secrets server-side. Verify `/api/health`, `/api/config`, authenticated event reads and `/mcp` initialization.
3. **Vercel owner:** set **Root Directory: `frontend`**, deploy main after merging PR #2, and set server-only `BACKEND_ORIGIN=https://your-backend-host` (origin only, no `/api`). Set public build variable `VITE_PUBLIC_MCP_URL=https://your-backend-host/mcp`, then redeploy. The frontend includes `vercel.json` and a server function forwarding `/api/*`. This configuration does not deploy Python or host MCP. The proxy forwards the caller's auth and injects no credentials.
4. **Go account owner:** install/authorize the backend MCP connector in standalone Go. In website Settings, check the event API and connect the same organizer. Run the synthetic prompt above and compare saved ID/revision and exact fields. Returning to the window refreshes events; visible pages also check every ten seconds. Change the location and confirm the same ID plus a newer revision.

Actual Vercel routing, standalone Go authorization and the full transfer remain unverified. Proxy checks use mocked upstream responses. See [Vercel function API](https://vercel.com/docs/functions/functions-api-reference) and [quickstart](https://vercel.com/docs/functions/quickstart).

## Live organizer adapter (Member 1, current)

This section supersedes the earlier details-only integration notes. Settings now connects `createOrganizerGateway` after existing-account Supabase sign-in. The initial screen still opens the labeled local preview, with no signup gate. All private REST requests carry the organizer access token, held only in memory. Disconnect, expiry or closing/reloading the page removes that session.

The adapter uses the implemented Member 2 endpoints:

| Action | Actual REST boundary |
| --- | --- |
| List/read | Paginated `GET /api/events`, canonical `GET /api/events/{id}` |
| Create/edit | `POST /api/events` with a stable retry `Idempotency-Key`; full `PUT /api/events/{id}` with `expected_revision`; server creates guest IDs |
| Prepare | `POST /api/events/{id}/prepare`, displaying its real queued/awaiting-Go receipt |
| Load material | `GET /api/events/{id}/review`, `/operations`, `/rsvps`, and signed `/artifacts/{flyer_png\|event_document}/current` links |
| Review prose | `POST /api/content/{id}/review`; edited content uses the returned replacement record on refresh |
| Authorize distribution | `POST /api/events/{id}/approvals`, bound to the exact invitation ID shown in the organizer's preview |
| Connect Go | `POST /api/connectors` issues a masked, in-memory personal token in Settings |

Publishing here records a durable approval and provides the exact Go `execute_distribution` prompt. It does not call a nonexistent publish endpoint, trigger Go automatically, or claim delivery. Missing current reviewed attachments or unavailable provider receipts block approval. An unknown approval outcome is not blindly retried; the integration owner must inspect stored approvals. Successful Gmail operation receipts establish sent history, and changes use a new change notice. Sent messages/attachments remain immutable. Without a readable Gmail binding, the organizer explicitly chooses first invitation versus change notice and Go must reconcile authoritative provider state.

The app refreshes connected data on window focus and every ten seconds while visible and clean. Unsaved changes pause polling; new writing/revisions reset the relevant editor only when its server version changes. Auth and revision conflicts surface instead of substituting sample data. An unavailable RSVP endpoint is labeled unavailable; private RSVP notes are excluded from the UI read model.

Inclusion facts are read-only because no fact-save endpoint exists. Unsourced or undated access confirmations remain unknown. No inclusion report, live queue feed, Gmail draft binding or Canva transaction approval is fabricated. A preparation receipt is a snapshot from this tab, not an execution-progress feed. Current artifact links come only from scoped signed server responses. No guessed Canva edit URLs or public Storage paths are constructed.

The frontend `/mcp` route now forwards the caller's Bearer and protocol headers to `BACKEND_ORIGIN/mcp`. This preserves a website-domain connector address after the backend is deployed and configured; it does not implement Python or authorize anonymous calls. Set `VITE_PUBLIC_MCP_URL` to the public connector address you actually use, then rebuild. The glass styles are preserved.

Verification: lint, TypeScript/Vite build and mocked HTTP/UI tests cover the above boundaries. The local sample dashboard was visually inspected at 1440×1000; exact 390×844 browser checks show no horizontal document overflow on dashboard, details and review. Full screen-reader verification, deployed authenticated integration, supported Grammarly assistance and real Go/provider rehearsal remain separate live checks.
