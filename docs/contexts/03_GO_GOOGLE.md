# Member 3 context: Superhuman Go, Google, synchronization, RSVP

Owner: Member 3 (human name/GitHub pending). Updated 2026-10-16. Status: **implemented and tested locally with mocks on `codex/member-3-go-google`; live Go/Google/Supabase unverified**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context. [Copy-ready prompt](../prompts/03_GO_GOOGLE.md).

## Scope

Own official Go connector/agent instructions, authenticated event MCP tools, `workflows/**`, Google provider adapters, Google account connection, sync/update jobs, email-reply RSVP handling, `main.py` composition, and Go integration docs. Coordinate shared dependencies/config with 2 and Canva/inclusion calls with 4.

## First deliverables

1. Prove Go reads an authorized test event and saves Go-written output through the hosted MCP connector. Verify actual account grants/triggers. Keep a visible manual Go-assisted queue fallback if website-triggered automation cannot be supported.
2. Make Go produce descriptions, plain-language summaries, invitation/change emails and document prose. Grammarly is part of Go, so it needs no separate integration (user decision 2026-10-16: Gemini and Notion dropped, `0d9ebf1`).
3. Implement one-writer Calendar/Gmail operations: stable event ID; deliberate notifications; stable draft tracking; new message/draft after sent; current flyer/document links and MIME attachments; operation receipts/idempotency.
4. Sync Calendar RSVP status and classify matched reply emails through Go. Ambiguous/forwarded/quoted/conditional replies require review; preserve source/provenance and prevent duplicate ingestion.

## Dependencies and handoffs

- Need from 2: authenticated principal, tenant-scoped repository/vault methods, event revisions, queue/approval/idempotency APIs and RSVP persistence.
- Need from 4: Canva/inclusion/document callable adapters and current revisioned artifact results.
- Supply to 1: Go execution status, provider operation status/receipts, links, RSVP state, and connection errors. Register 2/4 routers through the agreed composition point in `main.py`.

## Decisions and progress

- Agreed from user: Superhuman Go and Grammarly power writing/coordination; Gmail, Calendar and reply-based RSVP are core.
- **2026-10-16 | `codex/member-3-go-google` | implemented, tested (local/mocked) | executor decision:** the backend OAuth adapters are the single writer for Calendar and Gmail. Go writes prose and classifies replies through our MCP tools, and its own native Gmail/Calendar write actions stay disabled for this agent (`integrations/superhuman/agent/INSTRUCTIONS.md`). Reason: idempotency keys, provider IDs and receipts live in one place.
- **2026-10-16 | implemented, tested (local/mocked) | per-organizer MCP tools** (`mcp_tools/event_tools.py`): `get_event` (no emails/owner), `list_go_work`, `claim_go_work`, `save_generated_content` (producer fixed to `superhuman_go`, `expected_revision` CAS), `preview_distribution`, `execute_distribution` (requires organizer approval ID), `sync_rsvps`, `get_reply`, `record_rsvp_classification`, `list_rsvps` (private notes excluded). Each call resolves its bearer token to a principal; the global `MCP_AUTH_TOKEN` reaches only the scaffold tools.
- **2026-10-16 | implemented, tested (mocked HTTP) | Google** (`providers/google/**`, `workflows/distribution.py`, `workflows/rsvp.py`):
  - Calendar: a deterministic event ID, and a 409 adopts the existing event. Changes patch the same ID with If-Match and `sendUpdates=all`. The app revision is verified by read-back.
  - Gmail: invitees go in Bcc. An unsent draft is replaced in place. After a send, a `change_notice` is required in the same thread. Gmail is reconciled before acting, so a draft sent manually or a crash after send never causes a resend.
  - RSVP: Calendar `responseStatus` is mapped. A reply must match both the invitee and the thread. Forwarded, conditional, low-confidence or unquoted replies stay `needs_review`. Calendar/email conflicts are flagged. Private notes are organizer-only.
  - Evidence: 106 backend tests pass on Python 3.11 and 3.14. None of the following is live-verified: Google 409 on a duplicate ID, Bcc stripping, a 412 on a stale etag, or calendar.events scope limits.
- **2026-10-16 | implemented | dev mode** (`workflows/dev.py`, `WORKFLOW_DEV_MODE=1`): an in-memory store with one seeded test event, plus `/api/dev/*` routes (prepare, revise, approve, connect Google) guarded by `DEV_CONNECTOR_TOKEN`. This proves the live Go loop before Supabase lands. It is **not** Supabase evidence. Smoke-tested with a real uvicorn server and MCP over HTTP locally.
- **Website-to-Go trigger:** unverified. The fallback is the visible `awaiting_go` queue, which Go drains when the organizer says "Process my event work".
- Grammarly path (proposed): the organizer edits Go drafts in the website with the Grammarly extension, and edits are recorded as `producer: organizer`. Must be verified on the deployed page.
- **2026-10-16 | live (partial) | account setup:**
  - Google OAuth: a test project with External/Testing consent, and only the user's own Gmail as a test user. Web client redirect is `http://localhost:8000/api/dev/google/callback`. Calendar and Gmail APIs are enabled. The live consent grant succeeded with all five scopes.
  - Read-only `preview_distribution` returned over the public tunnel (create Calendar event and Gmail draft, blocked `awaiting_go`). Nothing has been sent.
  - Credentials are only in git-ignored `backend/.env.dev-go`.
  - The dev server needs `APP_DOMAIN=<tunnel host>`; otherwise MCP's DNS-rebinding check returns "Invalid Host header".
- **2026-10-16 | blocked | Go → MCP transport:**
  - Pack 72744 was uploaded and release 1 published from Pack Studio. The CLI `packs release` refuses to run while the tunnel URL sits uncommitted in `config.ts`.
  - The pack installed in Go (Connectors → search "Hackathon"; it is not listed until searched) and shows Connected.
  - Go's first chat said the tools were unavailable. Its session log shows `Mcp call init` → `POST https://<x>.trycloudflare.com/mcp <no HTTP response>` after **7 ms**, request ID `3e8ed224-…`. Neither the tunnel log nor the server log received it.
  - The same URL answers other external fetchers.
  - Follow-up tests on 2026-10-16:
    - A Go "Add custom MCP" connector (a pack with no auth) **did** reach the same trycloudflare URL from AWS IPs and got a 401 from us.
    - Pack v2 pointed at a localhost.run tunnel got a real HTTP 502 there. The free tunnel rotated its hostname mid-test, so it is unusable.
    - Pack v3, back on trycloudflare, again failed with `<no HTTP response>`.
  - So the failure is specific to authenticated pack requests to `trycloudflare.com`, not to all of Superhuman's traffic.
- **2026-10-16 | live, resolved | Go → MCP:**
  - After re-signing in to pack v3 with the token copied with no trailing newline (`tr -d '\n' | pbcopy`), Go called `list_go_work` over the trycloudflare tunnel and returned the queued `dev-event-1` `prepare_content` item (server: `POST /mcp 200`).
  - Likely root cause: a stray newline in the first pasted token makes the gateway fail before sending (`<no HTTP response>`, 7 ms). The domain was not blocked.
  - Each domain change in a pack release requires the user to sign in again.
  - Go asks for in-chat approval before each write tool (`claim_go_work`, `save_generated_content`).
- **2026-10-16 | live, tested | Go writing loop:**
  - After the organizer approved the tool calls in Go chat, Go ran `claim_go_work` → `get_event` → `save_generated_content` ×3 on `dev-event-1` revision 1.
  - Server state: the work item is `succeeded`; `invitation` (with subject), `description` and `summary` are saved as `producer: superhuman_go`, `needs_review`.
  - The drafts keep unknowns ("not yet confirmed" for entry, step-free access, captions, diet). They contain no invitee emails, only the organizer contact.
  - This is in-memory dev mode, not Supabase. Nothing was sent.
- **2026-10-16 | live, tested | publish:** the organizer approved the invitation via the dev approve route, with the user's explicit send confirmation in chat. `execute_distribution` over MCP, revision 1:
  - Operations: `calendar_upsert` created a real Google Calendar event (deterministic ID), then `gmail_draft`, then `gmail_send`, all `succeeded` with attempts=1.
  - It was sent to the single authorized test inbox only.
  - Retrying with the same approval reused all three receipts. Attempts stayed at 1, and the server log shows exactly one Gmail send call. Retry idempotency is verified live.
- **2026-10-16 | live, tested | change:**
  - Revision 2 moved the event to 7–9 PM at Golden Gate Park.
  - Go wrote rev-2 description, summary, invitation and `change_notice` through MCP after the organizer's in-chat approvals.
  - The `update` approval went through `execute_distribution`: the Calendar was patched on the **same event ID**, and a new change-notice draft was created and sent in the **same Gmail thread** (the prior message was already sent, so `new_change_notice`).
  - Retrying reused all receipts with attempts=1.
  - `sync_rsvps`/`list_rsvps` run live and return `no_response`; no guest reply had arrived yet. Reply classification is not yet live-verified.

- **2026-10-16 | main | implemented, tested (local/mocked; 300 backend tests pass, `npm run check` green) | integration:**
  - **Composition** (`main.py`):
    - `SUPABASE_URL` + `SUPABASE_PUBLISHABLE_KEY` turn on Member 2's REST router at `/api`.
    - Adding `SUPABASE_SERVICE_ROLE_KEY` builds `create_tool_dependencies`, so MCP tools, organizer tools and asset services all share one Supabase store with the website.
    - Dev mode is unchanged, and an unconfigured app still starts.
  - **Production Google connect** (`workflows/google_connect.py`):
    - `POST /api/google/connect` (Supabase session) → `GET /api/google/callback` → `SupabaseCredentialVault`; `GET /api/google/status`.
    - The OAuth state is random, single-use, owner-bound, valid for 10 minutes, and kept in memory (single instance only).
  - **Go organizer tools** (`mcp_tools/organizer_tools.py`):
    - `list_events`, `create_event`, `list_tasks`, `create_task`: creates take an idempotency key.
    - `update_event`, `update_task`: take `expected_revision` and apply partial updates that keep invitees.
    - All return the saved id and revision; the owner comes only from the token.
    - An event update does not queue Go preparation; the organizer re-prepares and approves in the website.
  - **Assets** (`workflows/asset_wiring.py`):
    - Member 4's preparation service, Go queue and Canva session are composed.
    - Go MCP tools: `get_event_assets`, `request_asset_prose`, `prepare_event_document`, `start/poll/preview/export_canva_flyer`.
    - Organizer routes under `/api/events/{id}/assets`, including `/flyer/approve` (exact preview digest) and `/flyer/abandon`.
    - Without a Canva token, these report `integration_not_connected`.
    - `Distributor` gets an `attachment_policy`: a started flyer must be stored and deliverable for the current revision before any Calendar or Gmail call. Preview shows a blocker and execute refuses with no side effects.
  - **Not live-verified:** the Supabase REST round trip, connector-token resolution in the database, the production Google consent → vault path, and Canva export → Storage → attachment.
  - **Deploy steps:** `docs/SUPERHUMAN.md#deploy`.

## Handoffs (proposed, awaiting recipient agreement)

- **Member 2 (from integration, 2026-10-16):**
  - **Deployment:**
    - The `backend/Dockerfile` start command must honour `$PORT`, turn on proxy headers, and default `APP_DOMAIN` from `RENDER_EXTERNAL_HOSTNAME`.
    - `.dockerignore`: add `.env.*`, `!.env.example`, `tests/`.
    - Add a `render.yaml` blueprint (see SUPERHUMAN.md).
  - **Canva:**
    - A Canva OAuth connect/refresh flow that writes vault provider `canva` as `{access_token}`.
    - A durable table and lease for flyer job state, replacing the vault-held state and the in-process lock.
  - **Google:** expose a token-cache forget hook so a Google reconnect takes effect immediately.
  - **Contract:** add the `/api/google/*` and `/api/events/{id}/assets/*` routes.
  - **Tenancy:** confirm that owner filtering in the `organizer_write_record` RPC (admin DB) is acceptable tenancy for Go's organizer tools.
- **Member 1:** add UI for flyer preview, approve and abandon; distribution blockers; and the Connect Google button (`POST /api/google/connect` → open `authorization_url`). The callback returns JSON today; agree on a redirect page.

- **Member 2:**
  - Implement the `WorkflowStore` Protocol (`workflows/ports.py`) on Supabase: owner-scoped, `save_content` CAS on the event revision, and an atomic work-item insert per `payload.idempotency_key`.
  - Implement `PrincipalResolver.resolve(token)` for per-organizer connector tokens (store SHA-256 hashes only).
  - Implement `CredentialVault` (`providers/google/oauth.py`) as encrypted refresh-token storage.
  - Provide a REST route that creates `Approval` records from the organizer's click.
  - Add these env names to `config.py` and `.env.example`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `WORKFLOW_DEV_MODE`, `DEV_CONNECTOR_TOKEN`, `DEV_INVITEES`, `DEV_ORGANIZER_CONTACT`.
  - Add the five asset `ContentKind` values to the canonical contract.
- **Member 4 (implemented on my side, tested locally):** `workflows/asset_queue.py`:
  - `GoAssetQueue.enqueue(ProseRequest)` conforms structurally to `GoPreparationQueue`. It checks owner and current revision, dedupes by `idempotency_key`, and returns `awaiting_go`/`queued` receipts. The asset batch supersedes only older asset batches, never invitation prep.
  - `load_go_content(...)` returns `GoContent` fields from server records (`generation_id` = content ID; `reviewed_by_organizer` = state `ready`).
  - Still needed from 4: `AttachmentSource.current_attachments(owner_id, event)` for MIME flyer attachments (currently `None`, so no attachment is sent), and the Canva session/tool-name map before I register adapters in `main.py`.
- **Member 1:** to show status, read the dev `GET /api/dev/events/{id}` shape until Member 2's API exists: work states, content `state` (`needs_review`/`ready`), operations (`state`, `error_code`, `receipt`), calendar and gmail bindings, and RSVPs with a `conflict` flag.

## Blockers / next action

1. Host the backend on a non-quick-tunnel HTTPS domain that Superhuman's fetcher reaches, or confirm with Superhuman why `trycloudflare.com` gets no response. Then re-run `npm run configure`, upload, and release. (Done: the Google OAuth client and the Pack install.)
2. Live proof: Go → `list_go_work` → `get_event` → `save_generated_content` on `dev-event-1`. Then run publish → revise → change notice → RSVP against authorized test inboxes only.
3. Merge with Member 2's repositories and Member 4's branch, then swap the in-memory store in composition.

## Update format

`Date | branch/commit/PR | status | capability/decision/source | tool/provider contracts | local vs mocked vs live evidence | blocker | next owner/action`. Never claim a scheduled/manual fallback is real-time website automation, or a draft is a sent message.
