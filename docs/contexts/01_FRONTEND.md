# Member 1 context: frontend

Owner: Member 1 (Tanay's checkout). Updated 2026-10-16, America/Los_Angeles.
Status: **implemented and tested locally with synthetic fixtures; organizer API/provider integration blocked on contracts and account setup**.
Branch: `codex/member-1-frontend`, based on `3bd33b3`.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), all four member contexts, [contract](../INTEGRATION_CONTRACT.md), and [assigned prompt](../prompts/01_FRONTEND.md) before work. Write only this personal context. Preserve other members' changes.

## Standalone Go → structured workspace transfer — 2026-10-16

**User goal | agreed:** users describe the entire event freely in the standalone Superhuman Go app, including event facts and Canva design preferences. No prescribed wording, order, or manual JSON should be required. Go interprets that request and invokes typed MCP tools; the backend validates/stores their data and the website places each record using its explicit schema. Ambiguous/missing dates, timezone, venue facts or design instructions require Go follow-up or preserved unknowns; arbitrary wording is not a guarantee that an ambiguous request can be inferred correctly.

**Implemented (frontend-owned):** `frontend/src/content.ts` exhaustively routes Go content kinds into Event details, Canva design, Inclusion, Documents, and Distribution. Flyer brief/copy/alt text and optional Notion output are now accepted (previously the UI rejected them). Legacy `summary`/`document` map to `plain_language_summary`/`event_document`. Email subjects are preserved, editable, and displayed in distribution. Edits match stable content IDs rather than array positions. Current and stale outputs retain their revision; body keywords never overwrite canonical event fields. Unknown kinds and duplicate content IDs fail visibly. Member 4 metadata (`flyer_png`/`event_document`, `review_state`) maps into the artifact view; content hashes produce UI keys only, and preview URLs remain absent until supplied. Cross-event content/artifact IDs are rejected when their event_id is present. Current-revision previews take precedence over older exports.

**Implemented composition seam:** `App` can accept an already-authenticated `EventGateway`; refresh reads its event list/details, with the same UI used for manual edits. Its default remains the local preview, preserving the requested skipped signup gate without exposing private records. The live adapter retains publish idempotency/revision behavior. This does not activate live REST or automatic browser subscription updates. The sample design brief is synthetic and explicitly covered by the preview label.

**Tested:** lint, production build, whitespace checks, and **23 frontend tests** pass. Added tests cover all tool content kinds/aliases in mixed order, keyword-rich bodies staying in their typed destinations, preserved subjects/revisions, unsupported/duplicate data errors, Member 4 metadata and cross-event rejection, and an injected gateway populating event fields/design/email groups on read/refresh. These are synthetic tool-output tests, not evidence of Go interpreting free-form language or a live transfer. No new browser visual audit or provider operation is claimed.

### Required next-owner handoff (proposed, not accepted)

- **Member 3:** add owner-scoped `create_event` and revision-checked `update_event` capabilities (names proposed) using Member 2's canonical repository. Existing `save_generated_content(event_id, expected_revision, kind, body, subject?, work_id?)` can store all supported prose/design kinds. Persist design requests as `flyer_brief`, not an unstructured blob in the event location/description. Canonical event facts go to typed event fields; provider outputs go through Member 4's validated asset services. Ask Go to confirm ambiguous dates/timezone and clarification items before writing required fields. Do not make the client infer destination from prose. Retain an exact target event ID for updates; do not create a new event on every revision. Creation/update and preparation must not silently authorize distribution.
- **Member 2:** finalize organizer-scoped list/detail/read/review schemas and durable storage shared by MCP and manual REST edits. Provide the already-authenticated browser gateway/identity handoff while signup is skipped. Supply a supported push/poll/read revision contract for Go-written changes to appear automatically. Event input must never trust client/Go-supplied owner_id, and ambiguous required facts must not be silently filled with defaults.
- **Members 3/4:** record actual Canva design/export/document IDs and revision after the chosen single executor succeeds; return authorized preview/edit/current URLs and source/approval metadata. Text instructions and a real exported flyer remain distinct records.
- **Integration proof required:** start with no event, describe a synthetic event/design in two differently worded Go prompts, observe typed create/save tool receipts and one canonical ID; verify website fields/design outputs, then change one detail and confirm a new revision on the same event. Missing timezone should prompt clarification. Retry should not duplicate the event. Actual invites remain behind organizer distribution approval.

**Inspected evidence:** upstream Member 3 `40304bb` has get/queue/claim/save-content/distribution/RSVP tools but no create/update event tools. Upstream Member 4 `a45a0be` adds user-authorized standalone Canva sample evidence, not Go → website/Supabase proof. Neither branch was merged or modified. This goal is **not yet working end to end**: missing server tools, shared persisted event API, organizer identity/account grants, and standalone Go round-trip proof remain outside Member 1 ownership. Only frontend and this context changed.

## Current UI simplification — 2026-10-16

**User request | agreed, implemented:** skip signup/login for now and open directly into the organizer space. Sidebar has exactly **Your events**, **Settings**, and **Profile**. Event cards and a plus button lead to **1. Event details → 2. Design & inclusion → 3. Distribution** inside each event. Removed the dashboard marketing hero/metrics and the separate provider/RSVP sidebar destinations. Holiday/diet questions remain visible; access/sensory facts and editable writing previews are collapsed. Provider receipts and private guest responses are expandable inside distribution. Profile name/email edits are local to this tab.

**User clarification | agreed, implemented UI:** send the organizer to Superhuman Go, have them add the team's custom MCP connector, then prompt Go to update website records and provider materials. Settings and event step 2 now contain **Continue in Superhuman Go** (`https://go.superhuman.com/`), connector setup instructions, an optional public hosted `VITE_PUBLIC_MCP_URL`, and a copyable event-ID/revision prompt. The prompt requires saved previews and organizer approval before sending. Clipboard failure on insecure LAN pages falls back to selecting/copying the text. Opening the Go tab does not install a connector, submit a prompt, or prove a connected account. Official URL/connector path checked against [Superhuman connector help](https://support.grammarly.com/hc/en-us/articles/40642362241293-About-Superhuman-Go-agents-and-connectors).

**Current boundary:** the simplified shell opens the local in-memory preview directly. The earlier login screen is removed, and the existing proposed auth/REST adapter remains isolated for later integration. No real organizer API is activated by bypassing authentication. Live private data, MCP receipts, and cross-provider synchronization remain pending; current sample records are not connected to Go. Member 3 supplies the actual connector/hosted address and trusted event creation/update tools; Member 2 supplies accepted authenticated records/read APIs. Existing contract proposals below remain proposals, not agreements. Future account UI should be coordinated through Settings/Profile without restoring the initial signup gate unless requested.

**Tested:** lint, production build, and **18 tests** pass after simplification. Updated UI tests cover direct entry, exactly three sidebar destinations, internal event stages, plus/create flow, official Go links, event-scoped prompts, missing-MCP setup messaging, inclusion/source gates, local profile editing, provider/RSVP sections, and backend errors. LAN root again returned HTTP 200. Native browser QA could not complete while the user's active Chrome session was changing; no new desktop/mobile visual verification is claimed. LAN development server remains running. Only `frontend/**` and this personal context changed; PR #2 will be updated on the existing branch.

The remaining sections preserve the original implementation/API handoff history; login/dashboard descriptions there are superseded by this section.

## Accepted direction and scope

- **2026-10-16 | user request | agreed:** implement `frontend/**` during this assigned task. Superhuman Go remains the central writing/coordination agent. Product name remains undecided; “Event Workspace” is a descriptive UI label.
- **2026-10-16 | updated user request | agreed:** users primarily prompt Go; Go creates website tasks/events through our custom authenticated MCP tools. Manual creation and editing remain available. This adds an event-creation tool requirement to Member 3's previous read/queue/content MCP scope. The client does not invent a Go completion endpoint or run a second MCP server.
- **2026-10-16 | follow-up user request | agreed, implemented:** expose the local preview to teammates on the same Wi-Fi. Vite runs on `0.0.0.0:5173`; its Network URL was shared in chat and verified HTTP 200. The host must remain awake. Each browser has separate ephemeral sample data. No production deployment, invitations, external asset publication, or Devpost submission occurred.

## Delivered frontend

**2026-10-16 | implemented:** React/TSX login, dashboard/search, manual event details, design/inclusion review, distribution confirmation, updates/sync, and private RSVP screens. Responsive styles, skip link, native labeled fields/fieldsets, heading focus on screen changes, live status/error messages, disabled pending actions, and unsaved-change guards are included.

- `frontend/src/types.ts`: proposed normalized event/review/content/artifact/work/operation/RSVP/fact shapes, gateway port, safe HTTPS links.
- `frontend/src/api.ts`: preserved real `/api/health` and `/api/status` checks; proposed authenticated REST adapter, runtime validation, HTTP error mapping, revision CAS, publish idempotency keys, and Supabase password sign-in. Live mode is explicitly disabled by default.
- `frontend/src/preview.ts`: synthetic sample Go-origin event/writing, stale Calendar receipt, failed Gmail draft, and ambiguous/conflicting RSVP. In-memory CRUD increments revisions and invalidates reviews. Preparation remains awaiting Go; no content is generated. Preview publishing always rejects and its UI is disabled.
- `frontend/src/dates.ts`: IANA wall-time conversion independent of browser timezone; ambiguous/nonexistent daylight-saving times are rejected.
- Editable description, plain-language summary, invitation/change notice and document prose label Go, organizer edits, or explicit Gemini provenance. No Grammarly verification is claimed.
- Canva preview/edit/current links, artifact revision and alt-text slots render actual metadata when supplied; absent artifacts remain waiting. No fabricated Canva image or export is shown.
- Inclusion questions cover step-free entrance, elevator, diet, observances, captions, loud sound and strobes. Unknown remains unknown; yes/no facts require source and confirmation date. Findings show source/date/status. Review acknowledgment is revision-specific.
- Distribution requires current reviewed mail and current flyer/document metadata. Unsent draft replacement and a new notification after sent email have distinct text. No old attachment mutation is promised. Provider receipts remain separate from canonical event phase.

## API/auth proposal for Member 2 — awaiting agreement

The complete TypeScript shapes are in `frontend/src/types.ts`; the wire adapter is isolated in `frontend/src/api.ts`. These are **proposed UI shapes**, not an accepted or live backend contract.

| Request                          | Proposed input/output                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `GET /api/events`                | `EventRecord[]`; optional server-owned `created_via: superhuman_go/manual`                                         |
| `GET /api/events/{id}`           | `WorkspaceEvent`: event, content, work, assets, facts, findings, operations, rsvps, gmail binding, review_revision |
| `POST /api/events`               | `EventInput` → `WorkspaceEvent`; no owner_id from browser                                                          |
| `PATCH /api/events/{id}`         | event fields + expected_revision → current `WorkspaceEvent`                                                        |
| `POST .../prepare`               | expected_revision → snapshot with real queue receipt/state                                                         |
| `POST .../review`                | expected_revision, edited content, sourced facts, acknowledge_unknowns → snapshot                                  |
| `POST .../publish` or `.../sync` | expected_revision, action publish/update, idempotency_key; same `Idempotency-Key` header → snapshot                |

The backend must validate organizer identity, exact content IDs, trusted Go provenance, review/approval, asset freshness and recipients independently of UI gating. Reuse the idempotency key for a retry, including after a timeout. Operations currently normalize provider receipts to display text; Member 3's receipt dictionaries require server/adapter mapping. RSVP response observations/conflicts require mapping to the UI shape. Canonical summary/document aliases may need mapping to `plain_language_summary`/`event_document`.

Live auth settings (public values only): `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_EVENT_API_ENABLED=true` **after contract agreement**. Supabase password-grant access tokens stay in React memory; same-origin REST requests use Bearer auth. Expiry and local sign-out drop this tab’s session. No refresh/persistence, registration, recovery, global session revocation, or provider-account connection flow is claimed. Official auth reference: https://supabase.github.io/auth/ . Service-role, OAuth and connector tokens never belong in browser settings.

**Next owner/action:** Member 2 confirms or revises these shapes and supplies an organizer-scoped REST/auth environment with RLS/ownership tests. Member 1 then maps the adapter and runs actual authenticated CRUD/review/publish error cases. Public pages remain deferred until a separately approved public schema/link policy exists. Durable revision history/changed-field comparisons also need a backend history shape; current updates screen explains the revision flow and shows provider revisions.

## Go/workflow handoff for Member 3

**2026-10-16 | proposed:** add authorized create/update task/event MCP tools backed by the same canonical records as manual REST writes. Return the canonical ID/revision; capture trusted `created_via`. The dashboard refresh retrieves Go-created events. Push/realtime arrival remains unimplemented pending a contract. Go must not silently publish merely because it created a task.

Read upstream `origin/codex/member-3-go-google` at `40304bb`: its workflow/content states and draft/sent semantics inform this UI. Its dev endpoint is a different shape and is intentionally not exposed as Supabase/live production evidence. No dev connector token is shipped to browsers. Provide the accepted normalized read model and review/approval endpoints through Member 2. Member 1 does not claim Member 3 accepted this REST proposal or that Google/Go work is live verified.

## Asset/inclusion handoff for Member 4

Read upstream context/integration guide at `3768f4e` / implementation `cdf08bc`. Custom Canva creation, rather than template-first autofill, is reflected in UI. Member 1 accepts the need for private reports, actual preview metadata, source dates, current artifact revision, trusted Go alt text and exact Canva approval binding.

**Proposed next action for 2/3/4:** normalize `AssetRecord.preview_metadata()` and `InclusionReport` into the UI adapter, and provide an authenticated pending-transaction endpoint containing operation ID + preview digest + revision. Add a separate preview approval action before committing Canva changes. The current generic review button does **not** authorize/commit Canva transactions; no raw continuation token is accepted by the client. Sourced floor/elevator and observance interval models must remain authoritative on the server; frontend yes/no fields are organizer questions, not an inclusion engine.

## Verification evidence and limits

**2026-10-16 | tested locally:** `npm run lint`, `npm test` (**16 tests**), `npm run build`, and `git diff --check` pass. Tests cover editable provenance/review gates, unknown/unsourced inclusion, manual event creation, awaiting-Go behavior, disabled preview publishing, provider stale/failure states, private/conflicting RSVP evidence, semantic labels/heading focus, runtime response validation, auth headers, HTTP 401/403/409/404/503, revision conflict, prep deduplication, unsafe artifact links, and IANA/DST conversion.

**2026-10-16 | actual local HTTP:** unchanged baseline Python backend launched from a temporary environment on loopback; LAN Vite proxy `/api/health` returns `ok/backend`; `/api/status` reports MCP unconfigured, Go unverified, no optional model. LAN root returns HTTP 200. This verifies the scaffold API/proxy only, not event API/Supabase/provider integration. Temporary Python installation uses existing declared dependency ranges; no shared lockfile/config changed.

**2026-10-16 | browser:** Chrome desktop login/dashboard visually inspected, accessible tree reviewed and dashboard screenshot captured in this chat. Native responsive-control attempts did not produce a usable mobile verification; responsive CSS is implemented but phone/browser audit and full screen-reader testing remain pending. No screenshot file was committed. Existing locked jsdom dependencies warn that local Node 24.13.1 is older than their 24.15 requirement; the checks above nevertheless completed successfully. Dependency inputs were preserved.

**Blocked live gates:** accepted event REST/auth schema, Supabase project/public config + organizer test accounts, authenticated Go event-creation tool receipt, real generated prose, Grammarly supported-client proof, Canva transaction preview/approval/export, authorized Storage/current URLs, Google connected-account receipts, authenticated publish/update/RSVP end-to-end proof. No credentials or private attendee data were stored in Git.

## Branch handoff

Only `frontend/**` and this personal context changed. Other member contexts and canonical docs remain untouched. Implementation commit: `8b8b897`. Draft [PR #2](https://github.com/Josh-Roe/SuperhumanGo_HackProj/pull/2) carries the local-preview implementation and marks live integrations as pending. Branch pushed to origin; local lint/tests/build and real scaffold API proxy checks passed as described above. Preserve the original pre-existing scaffold disclosure from the shared project docs.
