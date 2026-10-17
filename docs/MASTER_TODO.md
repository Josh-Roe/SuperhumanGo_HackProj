# Master to-do: everything left before the spec is met

Snapshot 2026-10-16 (America/Los_Angeles), main at `64eaa74`. Written for agents. Read [AGENTS.md](../AGENTS.md) and the four [contexts](contexts/) first. Those files take precedence over this list. Never record secrets or private RSVP data here.

## How to contribute (all agents, read before editing)

The user has authorized every member's agent to edit this file. This is an exception to AGENTS.md's rule that only Member 2 edits coordination docs. It is still not a place for progress diaries: detailed evidence stays in your own context, and this file holds one line of status per task.

1. **Sync first.** Run `git pull` before reading or editing this file, and again right before committing. Other agents edit it in parallel.
2. **Claim before starting.** Change `- [ ]` to `- [~]` and append `**Claimed:** Member N, YYYY-MM-DD HH:MM PT, branch`. Commit and push the claim by itself right away so nobody duplicates the work. Skip an item someone else has claimed. If a claim is more than 2 hours old with no linked commit, you may take it over: note `took over from Member N` on the item.
3. **Status markers.** `- [ ]` open, `- [~]` claimed or in progress, `- [x]` done, `- [!]` blocked. A blocked item gets `**Blocked:** <exact missing input, e.g. "Render env SUPABASE_SERVICE_ROLE_KEY unset"> → needs <M-item or Member N>`.
4. **Done means evidence.** Mark `[x]` only after the item's verify step passes. Append `**Done:** <commit SHA or PR> — <local | mocked | live>: <one-line proof>`. Examples: `pytest 320 passed`, `curl /api/health → 200`, `Calendar event id abc123 same after rev 2`. Mocked or local evidence never completes an item whose wording says live. Leave it `[~]` and say what remains.
5. **Edit only your item's lines.** Don't rewrite, reorder or reword other items. If you think another item is wrong, add an indented `- Note (Member N, date): …` under it.
6. **Adding tasks.** New tasks take the next free ID: **next manual = M12, next agent = A20**. Bump these numbers in the same edit. IDs are permanent: never renumber or reuse one. Put the task under the right owner heading with files, change and verify step. Cite where the need came from (spec line, context handoff, failing check). Add it to §4 if it is on the critical path.
7. **Never delete tasks.** If a task is obsolete, mark it `[x]` and strike it through: `~~text~~ **Dropped:** <reason, who decided>`. Cutting scope listed in §4 needs the user's or team lead's decision. Record who made it.
8. **Keep §1 true.** When your evidence changes a row in the Current state table, update that row and the snapshot line (date + main SHA).
9. **Joining with prior work (one-time reconcile).** If you already did work for your member before reading this file, do this before anything else, in a single commit (`todo: reconcile Member N`):
   - **Done items:** for each item your work finished, mark it `[x]` with evidence per rule 4.
   - **Partial items:** mark them `[~]` with what is left.
   - **In-progress work:** claim the items you are working on right now.
   - **Missing tasks:** add any your context or handoffs know about but this file lacks, per rule 6. That includes requests you made of other members that are still open.
   - **Current state:** correct any §1 row your evidence contradicts.

   Check against git history, not memory. If something can't be verified now, say so on the item.
10. **Commit separately.** Commit to-do edits on their own or together with the code they report, with messages like `todo: claim A5` or `todo: done A5 (abc1234)`. If a push is rejected, merge `origin/main` and keep both sides' edits. Never force-push.

**Deadline:** Devpost submission at 8:00 PM Pacific ([HACKATHON.md](HACKATHON.md)).

**Definition of done** (AGENTS.md final demo, all live, none mocked): create event → Go prepares assets and invitation → inclusion review → publish → change time/location → verify Calendar (same ID), draft or new email, and Canva revisions → collect RSVP.

Tags: `[MANUAL]` needs a human with an account, browser, dashboard or judgment. `[AGENT]` is repo work an agent can do and verify locally. `Owner` is the member number from AGENTS.md. An agent working outside its owner's paths needs the user's explicit authorization.

## 1. Current state

| Demo step | Evidence today | Gap |
| --- | --- | --- |
| Backend hosting | Render service `https://superhuman-go-event-backend.onrender.com` exists, but `/api/health` and `/mcp` return no response (checked 2026-10-16). Likely cause: `backend/Dockerfile` hardcodes `--port 8000`, while Render injects `PORT`. | A host that answers (see A1, M1) |
| Website | `https://mtcxhackathon1.vercel.app` serves the frontend. `/api/*` returns 503 because `BACKEND_ORIGIN` is unset. | M2 |
| Create event via Go | `create_event`/`update_event` MCP tools are implemented and tested (mocked). They return `dashboard_url` when `APP_URL` is set. Not live against Supabase. | M1–M5, A2, A3 |
| Go prepares prose | Live in **dev mode** (in-memory, `dev-event-1`): Go saved description, summary, invitation, change notice. Not live on Supabase. | Re-run on Supabase (M8) |
| Canva flyer | Services and MCP tools composed; without a Canva token they report `integration_not_connected`. No live export. | M6, A7, A8 |
| Inclusion review | Service implemented and tested locally. Holiday check (`0d9ebf1`) runs every review against Google's public Christian, Jewish, Muslim, Hindu and Orthodox feeds; a local run against the real feeds flagged Yom Kippur, Christmas, Diwali and Eid (from the eve). An authenticated `POST /api/events/{id}/assets/inclusion` exists, but the website never calls it (`findings: []` in `frontend/src/live.ts`) and facts are not saved. | A9, A10, A17 |
| Publish (Calendar + Gmail) | Live in dev mode: real Calendar event + Gmail send to one test inbox, retry idempotent. | Re-run on Supabase via website approval |
| Change time/location | Live in dev mode: same Calendar ID patched, change notice in same Gmail thread. | Same, plus Canva revision |
| RSVP | `sync_rsvps` live returns `no_response`. Reply classification is not live-verified. | M8 |
| Grammarly | Dropped (user decision 2026-10-16). | None |
| Tests | 313 backend tests pass on `e052761` (rerun by Member 3); frontend 52 tests pass (User 3, `c524b06`/`64eaa74`, local). | Keep green |

## 2. Manual tasks `[MANUAL]`

Do these roughly in order. Each one that unblocks an `[AGENT]` item names it.

### Hosting and deployment

- [ ] **M1 — Get Render answering.**
  - Note (Member 3, 2026-10-16): `/api/health` → 200, `/mcp` → 401, `/api/events` → 401. `/api/google/status` → 404, so the `GOOGLE_*`/`CREDENTIAL_ENCRYPTION_KEY` env vars look unset (Google connect only registers when they are set). Owner 2. Open the Render dashboard → service → Logs. If the issue is the port, set env `PORT=8000` as a stopgap until A1 lands. Set env: `APP_DOMAIN=superhuman-go-event-backend.onrender.com`, `APP_URL=https://mtcxhackathon1.vercel.app`, `MCP_AUTH_TOKEN`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://superhuman-go-event-backend.onrender.com/api/google/callback`. Leave `WORKFLOW_DEV_MODE` unset. Done when `curl https://superhuman-go-event-backend.onrender.com/api/health` returns 200 and an unauthenticated POST to `/mcp` returns 401. Free tier sleeps, so wake it before any demo.
- [ ] **M2 — Point Vercel at Render.** Owner 1 or 2. Vercel project (root `frontend`) env: `BACKEND_ORIGIN=https://superhuman-go-event-backend.onrender.com/` (server-only) and `VITE_PUBLIC_MCP_URL=https://superhuman-go-event-backend.onrender.com/mcp`, then redeploy (`VITE_*` is baked at build time). Done when `https://mtcxhackathon1.vercel.app/api/health` returns 200.
- [ ] **M3 — Google OAuth client.** Owner 3. In Google Cloud Console, add redirect URI `https://superhuman-go-event-backend.onrender.com/api/google/callback`. Add every test organizer and invitee as OAuth test users.
  - Note (Member 3, 2026-10-16): as of the last change in this session, the client lists only the dev redirect `http://localhost:8000/api/dev/google/callback`, and the user's own Gmail is the only test user (03 context). The production route exists in `d5ce546`. The console was not rechecked during this reconcile.

- [ ] **M11 — Apply the Gemini/Notion migration.** Owner 2. Apply `supabase/migrations/20261017010000_remove_gemini_and_notion.sql` (`0d9ebf1`) to project `qkfebdbwrmpisejnazud`. It narrows the `generated_content` kind and producer checks, and it stops with an error rather than deleting if any row still uses `notion_note` or `gemini`. Done when the migration shows as applied and inserting `producer='gemini'` is rejected. Source: user decision 2026-10-16 to drop Gemini and Notion; not applied because no Supabase CLI is available on Member 3's machine.

### Superhuman Go

- [ ] **M4 — Repoint the connector to Render.**
  - Note (Member 3, 2026-10-16): the Render build is uploaded (A4). Remaining: Release in Pack Studio → Go → Connectors → sign in again with an organizer token. Owner 3. After M1: run `npm --prefix integrations/superhuman run configure -- https://superhuman-go-event-backend.onrender.com/mcp`, then `check` and `upload` (an agent can run these if the Pack CLI is logged in; see A4). Release from the Pack Studio web UI. Then, in Go → Connectors, sign in again with an organizer token (no trailing newline). Done when Go runs `workspace_status` and `list_events` successfully.
  - Note (Member 3, 2026-10-16): pack 72744 v3 proved Go → MCP live in dev mode via a quick tunnel (`ea41bef`, `13605de`). That tunnel was shut down on 2026-10-16, so the installed connector now points at a dead host until this item lands. Render `/api/health` still did not answer at reconcile time (curl timeout).
- [ ] **M5 — Organizer account setup.** Each demo organizer: sign in at the website, Settings → "Create personal Go token" (use it in M4), then Connect Google (`POST /api/google/connect`) and check that `GET /api/google/status` shows connected.
- [ ] **M6 — Canva.** Owner 4. Get an eligible Canva account, the flyer template and its fields, and the Canva app credentials. Record their names (never values) in the 04 context. Unblocks A7 and A8.
  - Note (user decision, 2026-10-16): no team Canva account and no template. Each organizer connects **their own** Canva (per-organizer token in the vault, already how `connect_canva` works; custom design per event per the 04 context). What M6 still needs is only a registered Canva OAuth client (app client ID/secret, plus redirect URI) so organizers can connect their Canva via A11's connect flow. Record names, never values.
- [x] ~~**M7 — Grammarly proof.** Owner 3 or 4. In a supported Grammarly or Superhuman client, show Grammarly assistance on Go-written event prose. Record a screenshot outside Git and note it in the context.~~ **Dropped:** user decision 2026-10-16, Grammarly is out of scope entirely.

### Live proof and submission

- [ ] **M8 — Full live rehearsal on Supabase.** Everyone. Use authorized test inboxes only. Steps: ask Go to create an event (open its `dashboard_url`) → prepare assets → website inclusion review → website approval → Go `execute_distribution` → change the time and location through Go or the website → re-prepare, approve and execute → a second test account replies "yes" and accepts in Calendar → `sync_rsvps`/`list_rsvps`. Capture receipt IDs (Calendar event ID, Gmail message/thread IDs, Canva design/export IDs, revisions) in the 03 context. Requires M1–M6 and A2, A3 and A5.
- [!] **M9 — Accessibility audit.** **Claimed:** User 3, 2026-10-16 18:25 PT, `main`. Owner 1. ~~Real phone check and~~ a screen-reader pass on the deployed site. **Evidence:** `64eaa74` — local: six desktop AX/axe screens, skip-link keyboard check, focus fixes; 52 tests/lint/build pass. **Blocked:** native desktop bridge failed to start; actual screen-reader speech/control unavailable → needs local desktop VoiceOver pass (no deploy needed).
  - Note (user decision, 2026-10-16): phones are not a target; desktop only. Phone check dropped.
- [ ] **M10 — Devpost by 8 PM PT.** Team lead. Fill in: name (still undecided), primary track (working pick: Productivity), description, agent-integration write-up, demo video recorded from M8, repo plus working demo link and setup steps, all four member names, tools and credits including the **pre-existing scaffold disclosure** (HACKATHON.md). Before submitting, check that no link exposes keys or private data. Prepare the 2-minute live pitch ([PRESENTATION.md](PRESENTATION.md)).

## 3. Agentic tasks `[AGENT]`

Each item lists files, the change, and how to verify it. Run `uv run --project backend pytest` / `ruff check` or `npm --prefix frontend test`/`lint`/`build` before committing. Follow the testing rules in the user's CLAUDE.md: test behavior, keep tests few, parametrize, no loops.

### Owner 2: backend, Supabase, deploy

- [~] **A1 — Render-compatible container.** `backend/Dockerfile`: bind to `${PORT:-8000}`, use `--proxy-headers` with `FORWARDED_ALLOW_IPS="*"`, default `APP_DOMAIN` from `RENDER_EXTERNAL_HOSTNAME`, and make `HEALTHCHECK` read `PORT`. Exact CMD is in [SUPERHUMAN.md § Handoff to Member 2](SUPERHUMAN.md). `backend/.dockerignore`: add `.env.*`, `!.env.example`, `tests/`. Add a root `render.yaml` (docker runtime, `healthCheckPath: /api/health`, env names with `sync: false`, including `APP_URL`). Verify: `docker build` (or CI) and run with `PORT=10000`; check that `/api/health` returns 200. **Claimed:** Member 1 (User 1, lane L5), 2026-10-16 18:25 PT, main **Done so far:** ff8d7c6 — local: Docker not installed on this device, so ran the Dockerfile's exact shell-form CMD via uv with PORT=10000 → uvicorn on :10000, `curl /api/health` → 200, HEALTHCHECK command → 200; render.yaml parses (10 env keys incl. APP_URL); pytest 318 passed (1 failure from L1's uncommitted workflow files). Remaining: `docker build` (or CI), Render redeploy + curl /api/health (M1).
- [ ] **A2 — Live Supabase check of the Go tools.** Against project `qkfebdbwrmpisejnazud` with a synthetic organizer, check that connector-token resolution (`SupabasePrincipalResolver`), `create_event` → `list_events` → website `GET /api/events` all show the same id and revision. Roll the test data back as `supabase/tests/organizer_isolation.sql` does.
- [ ] **A3 — Contract docs.** `docs/INTEGRATION_CONTRACT.md`: add `/api/google/connect|callback|status`, the `/api/events/{id}/assets/*` routes (including `/flyer/approve` and `/flyer/abandon`), MCP organizer tools, and `dashboard_url`/`APP_URL`. Update `PROJECT_CONTEXT.md` evidence. README deploy section: Vercel `BACKEND_ORIGIN`/`VITE_PUBLIC_MCP_URL`, Render env list.
- [ ] **A18 — Confirm Go organizer-tool tenancy.** Owner 2. `task_repository` uses the admin `Database`; isolation for Go's `create_event`/`update_event` relies on the `p_owner` filter in `organizer_write_record`, not RLS. Confirm this is acceptable, or provide an RLS-scoped path. Verify: an isolation SQL test with two organizers through the RPC. Source: 03 context handoff (`d5ce546`).
- [~] **A10 — Read contracts the UI needs.** Owner-scoped REST reads for current Go work, Gmail binding (sent/draft IDs + revision), and approvals. Make approval creation idempotent and recoverable on reload. A versioned save endpoint for inclusion facts. Requested in 01 context. **Claimed:** Member 1 (User 1, lane L2), 2026-10-16 18:25 PT, main
- [ ] **A11 — Canva and Google plumbing.** Canva OAuth connect/refresh writing vault provider `canva` as `{access_token}`. A durable flyer-job table and lease, replacing vault state and the in-process lock. A Google token-cache "forget" hook so reconnects take effect immediately. Requested in 03 context.
  - Note (Member 1, User 1 lane L3, 2026-10-16 18:29 PT): **Claimed** the Canva part (OAuth connect/refresh + durable flyer-job table/lease), main. Google token-cache part is lane L1.

### Owner 3: Go, Google, composition

- [x] **A4 — Connector config for Render.** After M1 returns 401 on `/mcp`: run `configure` to the Render `/mcp`, `check`, `upload`, then commit `integrations/superhuman/config.ts`. **Never commit a `trycloudflare.com` host.** The working tree currently holds an uncommitted tunnel URL in that file: discard it only when replacing it with the Render URL. **Done:** `cb868ca` — live: Render `/api/health` → 200, unauthenticated `/mcp` → 401; `configure` → `check` (Pack is valid) → `upload` succeeded for pack 72744. Releasing in Pack Studio and signing in again are part of M4.
- [x] **A5 — Queue supersede fix.** `backend/src/hackathon_backend/workflows/go_work.py` `enqueue_preparation`: supersede only open work for **older** revisions, not the same revision. Member 2's repository deduplicates same-revision jobs, and superseding them breaks that. Add one test where same-revision re-enqueue keeps the job and an older-revision job is superseded. **Done:** `c28d6d8` — local: same-revision re-enqueue returns the same open job, and older-revision work is superseded (`test_reenqueue_keeps_same_revision_job_and_supersedes_older_revision`); pytest 308 passed.
- [x] **A6 — Go agent instructions.** `integrations/superhuman/agent/INSTRUCTIONS.md`: after `create_event`/`update_event`/`list_events`, give the organizer the returned `dashboard_url`. Never construct one when it is absent. **Done:** `c28d6d8` — local: `INSTRUCTIONS.md` tells Go to give the organizer the returned `dashboard_url` and never to construct one. Go must re-read the instructions in the agent builder (part of M4).
- [x] **A13 — Google callback UX.** `GET /api/google/callback` returns JSON today. Redirect to `APP_URL` with a success or failure flag that the frontend reads (agree on the shape with Member 1). OAuth state is held in memory, which is fine for a single Render instance; note this limit. **Done:** `c4eb9e9` — mocked: when `APP_URL` is set, the callback answers 303 to `{APP_URL}/?google=connected` or `?google=error&reason=invalid_state|denied|exchange_failed|no_refresh_token` (no tokens or email in the URL; read `GET /api/google/status`); without `APP_URL` it keeps the JSON responses. `test_google_connect.py`, pytest 319 passed. A16 should use this contract.
- [~] **A14 — Unknown-effect reconciliation.** **Claimed:** Member 3, 2026-10-16 18:45 PT, main; continued by Member 1 (User 1, lane L1), 2026-10-16 18:27 PT, main. Gmail create/send with an unknown outcome and crashed running operations are blocked until a server read-back exists. Implement read-back via `reconcile_operation` before any retry. Never retry blindly.
  - Note (Member 3, 2026-10-16): paused at the user's request. Partial, **untested and uncommitted** changes exist only on Member 3's machine: a Gmail read-back helper in `providers/google/gmail.py`, `reconcile_operation` on `workflows/ports.py` + `workflows/memory.py`. Remaining: wire the read-back into `distribution.py` before retrying an unknown-outcome or crashed-`running` op (adopt the receipt if the effect happened; retry once only if it provably didn't; otherwise `needs_review`), and add `tests/test_workflow_unknown_effect.py` (timed-out-but-sent → no resend; crashed Calendar → adopt; not sent → one send).

### Owner 1: frontend

- [x] **A15 — `?event=<id>` deep link.** **Claimed:** User 3, 2026-10-16 18:23 PT, `main`. `frontend/src/App.tsx`: on load (and once connected), read `new URLSearchParams(location.search).get("event")` and call the existing `openEvent(id)` (around line 1504). If the organizer is not connected yet, keep the id until they connect. Show "not found" for ids that are inaccessible or unknown. This makes Go's `dashboard_url` land on the event. Add a test. **Done:** `c524b06` — local/mocked: delayed/direct deep links and missing/foreign IDs; 52 tests, lint/build pass.
- [~] **A16 — Provider UI.** Add flyer preview with approve (exact preview digest) and abandon; distribution blockers from `preview_distribution`; a Connect Google button (`POST /api/google/connect` → open `authorization_url`) plus a status display; and the callback result page from A13. **Claimed:** Member 1 (User 1, lane L4), 2026-10-16 18:24 PT, main
- [ ] **A17 — Inclusion UI writes.** Once A10's inclusion-fact endpoint exists, enable editing with source and date. Keep `unknown` visible.
  - Note (Member 3, 2026-10-16): the server form differs from the website's: separate loud-sound and strobe facts, floor plus elevator, food served plus a diet list, structured `Source` (label, confirmed_by, observed_at, url), and `traditions` (which holiday calendars to check; all five by default, empty opts out). Show the returned `religious_observances` conflicts. See `services/inclusion/__init__.py`.

### Owner 4: Canva, inclusion, assets, pitch

- [ ] **A7 — Canva live path.** After M6: export flyer → `SupabaseAssetStorage.put_if_absent` → `publish_current` → attachment via `SupabaseAttachmentSource`. Verify a real upload and signed-URL round trip (currently unverified).
- [ ] **A8 — Canva revision on change.** On a new event revision, update the current design or create a new version and export, and record its revision. Old exports stay as immutable snapshots.
- [ ] **A9 — Inclusion report transport.** With 2 and 3: an authenticated inclusion-report route and pending Canva operation previews (operation ID, digest, revision, thumbnails, approval action) that the UI consumes.
- [x] **A19 — Canva pending-export poll.** Owner 4. `providers/canva` has no way to poll a pending export, so `/api/events/{id}/assets/flyer/export` requests a new export on each call until one completes. Add a poll or resume using the export job ID. Verify: a mocked test where a second export call polls the same job. Source: 03 context handoff (`d5ce546`). **Claimed:** Member 1 (User 1, lane L3), 2026-10-16 18:26 PT, main **Done:** `ad38df3` — mocked: second export call polls the same job (`GET /v1/exports/export-123`) and stores it; `export-design` called once; failed job allows a fresh export (`test_canva_export_poll.py`, 2 tests). Live poll needs M6 + an organizer Canva token.
- [ ] **A12 — Pitch assets.** `docs/PRESENTATION.md`: a 2-minute script that follows the final demo, plus the disclosure slide. Add `assets/**` for Canva deck exports.

## 4. Critical path

```text
A1 (Dockerfile PORT) ─┬─> M1 Render answers ─┬─> M2 Vercel BACKEND_ORIGIN ─> A15 deep link usable
                      │                      ├─> M3 Google redirect ─> M5 organizer connects Google
                      │                      └─> A4/M4 connector → Render ─> M5 Go token
A5, A6, A2 ───────────┴──────────────────────────────────────────────┐
M6 Canva ─> A7 ─> A8 ────────────────────────────────────────────────┤
A9/A16 UI for flyer + inclusion ─────────────────────────────────────┤
─────────────────────────────────────────────────────────────────────┴─> M8 live rehearsal ─> M10 Devpost video + submit (8 PM PT)
```

If time runs short, cut in this order. Each cut must be stated honestly in the demo and on Devpost:

1. Canva revision on change (A8): show the stale flag instead.
2. Inclusion fact editing (A17).
3. Reply classification: Calendar RSVP statuses only.

Never cut: live Go writing plus a provider receipt, organizer approval before sending, and the same-ID Calendar update.

## 5. Code first, docs last: four-user assignments

User decision, 2026-10-16: finish every coding task before writing any documentation (A3, A12, PRESENTATION, and context write-ups beyond one-line evidence). These assignments override the ownership table in AGENTS.md for the items listed here. This is the explicit user authorization AGENTS.md requires for working outside your own paths. Everyone still claims one item at a time (rule 2), not a whole queue.

**Who is who.** **User 1** is the user, on the stronger agentic plan; they have been acting as Members 1 and 3 and hold the Google Cloud console and Pack Studio access. **User 2** holds the Member 2 seat (Supabase, Render, Vercel). **User 4** holds the Member 4 seat (Canva, pitch). **User 3** is the fourth teammate.

| User | Coding | Manual | Docs (after all coding) |
| --- | --- | --- | --- |
| **1** | A14, A1, A10, A18, A11, A19, A9, A16, A17 (the lanes below) | M3 Google OAuth client, M4 Go connector release, M5 organizer accounts and test inboxes | — |
| **2** | A2 live Supabase check; review and apply the migrations from A10 and A11 | M1 Render env, M2 Vercel env, M11 Gemini/Notion migration | A3 contract docs, README |
| **3** | A15 `?event=` deep link | M9 screen-reader audit (on a local build; no deploy needed) | — |
| **4** | A7 live Canva export, A8 Canva revision on change | M6 Canva OAuth client, M10 Devpost | A12 pitch |
| **All** | | M8 live rehearsal (User 2 drives it, everyone joins) | |

**User 1's parallel lanes.** Each lane touches its own files, so the lanes can run as separate agent sessions at the same time. Within a lane, go top to bottom. Every item can be built and tested locally against mocks now. The manual task listed under "Live check waits on" only gates the live check, so leave the item `[~]` until it lands (rule 4). Each lane writes its own timestamped migration file, and User 2 applies them.

| Lane | Files (mostly) | Queue | Live check waits on |
| --- | --- | --- | --- |
| **L1 Workflows / Google** | `workflows/**`, `providers/google/**` | A14 → A11 (the Google token-cache forget part) | M1, M3, M5 (a real reconnect) |
| **L2 Backend API / Supabase** | `api/**`, `repositories/**`, `supabase/**` | A10 → A18 | User 2 applying the migrations; A18's SQL test needs Supabase access |
| **L3 Canva** | `providers/canva/**`, `services/assets/**` | A19 → A11 (Canva OAuth and the flyer-job table) → A9 | M6, plus an organizer connecting their own Canva |
| **L4 Frontend** | `frontend/**` | A16 (mocked against the A13/A10 contracts) → A17 (once L2 pushes the A10 endpoint shape) | M1, M2, M3 |
| **L5 Deploy** | `backend/Dockerfile`, `render.yaml` | A1 (small; run it first or alongside L1) | M1 (Render redeploy) |

Cross-lane handoffs:
- L4's A17 and User 4's A8 need L2's A10 endpoints. L3's A9 needs L2's read routes. Push those contracts first so the dependent work can mock against them.
- A7 and A8 also need L3's Canva OAuth work and M6.

All lanes share one checkout on `main` (no worktrees, per the user's CLAUDE.md). Commit only your lane's files, and pull before each commit.

**Manual work to start right away, alongside the coding:**
- M6 (User 4): it gates all live Canva work.
- M1 and M2 (User 2) and M3 (User 1): together they gate live Google and the website.
- M11 (User 2): it gates live L2 work and A2.

After those come M4 and M5 (User 1). User 3's tasks have no dependencies on anyone, so User 3 can start all of them now. M9 can happen whenever someone is free. M10 depends on the M8 recording.
