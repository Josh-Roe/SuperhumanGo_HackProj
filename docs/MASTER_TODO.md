# Master to-do: everything left before the spec is met

Snapshot 2026-10-16 (America/Los_Angeles), main at `afd1b2c`. Written for agents. Read [AGENTS.md](../AGENTS.md) and the four [contexts](contexts/) first. Those files take precedence over this list. Never record secrets or private RSVP data here.

## How to contribute (all agents, read before editing)

The user has authorized every member's agent to edit this file. This is an exception to AGENTS.md's rule that only Member 2 edits coordination docs. It is still not a place for progress diaries: detailed evidence stays in your own context, and this file holds one line of status per task.

1. **Sync first.** Run `git pull` before reading or editing this file, and again right before committing. Other agents edit it in parallel.
2. **Claim before starting.** Change `- [ ]` to `- [~]` and append `**Claimed:** Member N, YYYY-MM-DD HH:MM PT, branch`. Commit and push the claim by itself right away so nobody duplicates the work. Skip an item someone else has claimed. If a claim is more than 2 hours old with no linked commit, you may take it over: note `took over from Member N` on the item.
3. **Status markers.** `- [ ]` open, `- [~]` claimed or in progress, `- [x]` done, `- [!]` blocked. A blocked item gets `**Blocked:** <exact missing input, e.g. "Render env SUPABASE_SERVICE_ROLE_KEY unset"> → needs <M-item or Member N>`.
4. **Done means evidence.** Mark `[x]` only after the item's verify step passes. Append `**Done:** <commit SHA or PR> — <local | mocked | live>: <one-line proof>`. Examples: `pytest 320 passed`, `curl /api/health → 200`, `Calendar event id abc123 same after rev 2`. Mocked or local evidence never completes an item whose wording says live. Leave it `[~]` and say what remains.
5. **Edit only your item's lines.** Don't rewrite, reorder or reword other items. If you think another item is wrong, add an indented `- Note (Member N, date): …` under it.
6. **Adding tasks.** New tasks take the next free ID: **next manual = M11, next agent = A20**. Bump these numbers in the same edit. IDs are permanent: never renumber or reuse one. Put the task under the right owner heading with files, change and verify step. Cite where the need came from (spec line, context handoff, failing check). Add it to §4 if it is on the critical path.
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
| Inclusion review | Service and holiday-calendar checks implemented and tested locally. UI is read-only; no authenticated report route. | A9, A12 |
| Publish (Calendar + Gmail) | Live in dev mode: real Calendar event + Gmail send to one test inbox, retry idempotent. | Re-run on Supabase via website approval |
| Change time/location | Live in dev mode: same Calendar ID patched, change notice in same Gmail thread. | Same, plus Canva revision |
| RSVP | `sync_rsvps` live returns `no_response`. Reply classification is not live-verified. | M8 |
| Grammarly | Not demonstrated. | M7 |
| Tests | 313 backend tests pass on `afd1b2c`; frontend 51 tests pass (Member 1 context). | Keep green |

## 2. Manual tasks `[MANUAL]`

Do these roughly in order. Each one that unblocks an `[AGENT]` item names it.

### Hosting and deployment

- [ ] **M1 — Get Render answering.** Owner 2. Open the Render dashboard → service → Logs. If the issue is the port, set env `PORT=8000` as a stopgap until A1 lands. Set env: `APP_DOMAIN=superhuman-go-event-backend.onrender.com`, `APP_URL=https://mtcxhackathon1.vercel.app`, `MCP_AUTH_TOKEN`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://superhuman-go-event-backend.onrender.com/api/google/callback`. Leave `WORKFLOW_DEV_MODE` unset. Done when `curl https://superhuman-go-event-backend.onrender.com/api/health` returns 200 and an unauthenticated POST to `/mcp` returns 401. Free tier sleeps, so wake it before any demo.
- [ ] **M2 — Point Vercel at Render.** Owner 1 or 2. Vercel project (root `frontend`) env: `BACKEND_ORIGIN=https://superhuman-go-event-backend.onrender.com/` (server-only) and `VITE_PUBLIC_MCP_URL=https://superhuman-go-event-backend.onrender.com/mcp`, then redeploy (`VITE_*` is baked at build time). Done when `https://mtcxhackathon1.vercel.app/api/health` returns 200.
- [ ] **M3 — Google OAuth client.** Owner 3. In Google Cloud Console, add redirect URI `https://superhuman-go-event-backend.onrender.com/api/google/callback`. Add every test organizer and invitee as OAuth test users.
  - Note (Member 3, 2026-10-16): as of the last change in this session, the client lists only the dev redirect `http://localhost:8000/api/dev/google/callback`, and the user's own Gmail is the only test user (03 context). The production route exists in `d5ce546`. The console was not rechecked during this reconcile.

### Superhuman Go

- [ ] **M4 — Repoint the connector to Render.** Owner 3. After M1: run `npm --prefix integrations/superhuman run configure -- https://superhuman-go-event-backend.onrender.com/mcp`, then `check` and `upload` (an agent can run these if the Pack CLI is logged in; see A4). Release from the Pack Studio web UI. Then, in Go → Connectors, sign in again with an organizer token (no trailing newline). Done when Go runs `workspace_status` and `list_events` successfully.
  - Note (Member 3, 2026-10-16): pack 72744 v3 proved Go → MCP live in dev mode via a quick tunnel (`ea41bef`, `13605de`). That tunnel was shut down on 2026-10-16, so the installed connector now points at a dead host until this item lands. Render `/api/health` still did not answer at reconcile time (curl timeout).
- [ ] **M5 — Organizer account setup.** Each demo organizer: sign in at the website, Settings → "Create personal Go token" (use it in M4), then Connect Google (`POST /api/google/connect`) and check that `GET /api/google/status` shows connected.
- [ ] **M6 — Canva.** Owner 4. Get an eligible Canva account, the flyer template and its fields, and the Canva app credentials. Record their names (never values) in the 04 context. Unblocks A7 and A8.
- [ ] **M7 — Grammarly proof.** Owner 3 or 4. In a supported Grammarly or Superhuman client, show Grammarly assistance on Go-written event prose. Record a screenshot outside Git and note it in the context.

### Live proof and submission

- [ ] **M8 — Full live rehearsal on Supabase.** Everyone. Use authorized test inboxes only. Steps: ask Go to create an event (open its `dashboard_url`) → prepare assets → website inclusion review → website approval → Go `execute_distribution` → change the time and location through Go or the website → re-prepare, approve and execute → a second test account replies "yes" and accepts in Calendar → `sync_rsvps`/`list_rsvps`. Capture receipt IDs (Calendar event ID, Gmail message/thread IDs, Canva design/export IDs, revisions) in the 03 context. Requires M1–M7 and A2, A3 and A5.
- [ ] **M9 — Accessibility audit.** Owner 1. Real phone check and a screen-reader pass on the deployed site.
- [ ] **M10 — Devpost by 8 PM PT.** Team lead. Fill in: name (still undecided), primary track (working pick: Productivity), description, agent-integration write-up, demo video recorded from M8, repo plus working demo link and setup steps, all four member names, tools and credits including the **pre-existing scaffold disclosure** (HACKATHON.md). Before submitting, check that no link exposes keys or private data. Prepare the 2-minute live pitch ([PRESENTATION.md](PRESENTATION.md)).

## 3. Agentic tasks `[AGENT]`

Each item lists files, the change, and how to verify it. Run `uv run --project backend pytest` / `ruff check` or `npm --prefix frontend test`/`lint`/`build` before committing. Follow the testing rules in the user's CLAUDE.md: test behavior, keep tests few, parametrize, no loops.

### Owner 2: backend, Supabase, deploy

- [ ] **A1 — Render-compatible container.** `backend/Dockerfile`: bind to `${PORT:-8000}`, use `--proxy-headers` with `FORWARDED_ALLOW_IPS="*"`, default `APP_DOMAIN` from `RENDER_EXTERNAL_HOSTNAME`, and make `HEALTHCHECK` read `PORT`. Exact CMD is in [SUPERHUMAN.md § Handoff to Member 2](SUPERHUMAN.md). `backend/.dockerignore`: add `.env.*`, `!.env.example`, `tests/`. Add a root `render.yaml` (docker runtime, `healthCheckPath: /api/health`, env names with `sync: false`, including `APP_URL`). Verify: `docker build` (or CI) and run with `PORT=10000`; check that `/api/health` returns 200.
- [ ] **A2 — Live Supabase check of the Go tools.** Against project `qkfebdbwrmpisejnazud` with a synthetic organizer, check that connector-token resolution (`SupabasePrincipalResolver`), `create_event` → `list_events` → website `GET /api/events` all show the same id and revision. Roll the test data back as `supabase/tests/organizer_isolation.sql` does.
- [ ] **A3 — Contract docs.** `docs/INTEGRATION_CONTRACT.md`: add `/api/google/connect|callback|status`, the `/api/events/{id}/assets/*` routes (including `/flyer/approve` and `/flyer/abandon`), MCP organizer tools, and `dashboard_url`/`APP_URL`. Update `PROJECT_CONTEXT.md` evidence. README deploy section: Vercel `BACKEND_ORIGIN`/`VITE_PUBLIC_MCP_URL`, Render env list.
- [ ] **A18 — Confirm Go organizer-tool tenancy.** Owner 2. `task_repository` uses the admin `Database`; isolation for Go's `create_event`/`update_event` relies on the `p_owner` filter in `organizer_write_record`, not RLS. Confirm this is acceptable, or provide an RLS-scoped path. Verify: an isolation SQL test with two organizers through the RPC. Source: 03 context handoff (`d5ce546`).
- [ ] **A10 — Read contracts the UI needs.** Owner-scoped REST reads for current Go work, Gmail binding (sent/draft IDs + revision), and approvals. Make approval creation idempotent and recoverable on reload. A versioned save endpoint for inclusion facts. Requested in 01 context.
- [ ] **A11 — Canva and Google plumbing.** Canva OAuth connect/refresh writing vault provider `canva` as `{access_token}`. A durable flyer-job table and lease, replacing vault state and the in-process lock. A Google token-cache "forget" hook so reconnects take effect immediately. Requested in 03 context.

### Owner 3: Go, Google, composition

- [ ] **A4 — Connector config for Render.** After M1 returns 401 on `/mcp`: run `configure` to the Render `/mcp`, `check`, `upload`, then commit `integrations/superhuman/config.ts`. **Never commit a `trycloudflare.com` host.** The working tree currently holds an uncommitted tunnel URL in that file: discard it only when replacing it with the Render URL.
  - Note (Member 3, 2026-10-16): blocked on M1. The tunnel in the uncommitted `config.ts` is shut down.
- [~] **A5 — Queue supersede fix.** **Claimed:** Member 3, 2026-10-16 18:45 PT, main. Verified open: `enqueue_preparation` still supersedes same-revision work (`go_work.py` ~L49). `backend/src/hackathon_backend/workflows/go_work.py` `enqueue_preparation`: supersede only open work for **older** revisions, not the same revision. Member 2's repository deduplicates same-revision jobs, and superseding them breaks that. Add one test where same-revision re-enqueue keeps the job and an older-revision job is superseded.
- [~] **A6 — Go agent instructions.** **Claimed:** Member 3, 2026-10-16 18:45 PT, main. The `dashboard_url` field is returned (`6216594`); the instructions don't mention it yet. `integrations/superhuman/agent/INSTRUCTIONS.md`: after `create_event`/`update_event`/`list_events`, give the organizer the returned `dashboard_url`. Never construct one when it is absent.
- [~] **A13 — Google callback UX.** **Claimed:** Member 3, 2026-10-16 18:45 PT, main. Routes and state handling exist (`d5ce546`, mocked: `test_google_connect.py`); the redirect is still missing. `GET /api/google/callback` returns JSON today. Redirect to `APP_URL` with a success or failure flag that the frontend reads (agree on the shape with Member 1). OAuth state is held in memory, which is fine for a single Render instance; note this limit.
- [~] **A14 — Unknown-effect reconciliation.** **Claimed:** Member 3, 2026-10-16 18:45 PT, main. Gmail create/send with an unknown outcome and crashed running operations are blocked until a server read-back exists. Implement read-back via `reconcile_operation` before any retry. Never retry blindly.

### Owner 1: frontend

- [ ] **A15 — `?event=<id>` deep link.** `frontend/src/App.tsx`: on load (and once connected), read `new URLSearchParams(location.search).get("event")` and call the existing `openEvent(id)` (around line 1504). If the organizer is not connected yet, keep the id until they connect. Show "not found" for ids that are inaccessible or unknown. This makes Go's `dashboard_url` land on the event. Add a test.
- [ ] **A16 — Provider UI.** Add flyer preview with approve (exact preview digest) and abandon; distribution blockers from `preview_distribution`; a Connect Google button (`POST /api/google/connect` → open `authorization_url`) plus a status display; and the callback result page from A13.
- [ ] **A17 — Inclusion UI writes.** Once A10's inclusion-fact endpoint exists, enable editing with source and date. Keep `unknown` visible.

### Owner 4: Canva, inclusion, assets, pitch

- [ ] **A7 — Canva live path.** After M6: export flyer → `SupabaseAssetStorage.put_if_absent` → `publish_current` → attachment via `SupabaseAttachmentSource`. Verify a real upload and signed-URL round trip (currently unverified).
- [ ] **A8 — Canva revision on change.** On a new event revision, update the current design or create a new version and export, and record its revision. Old exports stay as immutable snapshots.
- [ ] **A9 — Inclusion report transport.** With 2 and 3: an authenticated inclusion-report route and pending Canva operation previews (operation ID, digest, revision, thumbnails, approval action) that the UI consumes.
- [ ] **A19 — Canva pending-export poll.** Owner 4. `providers/canva` has no way to poll a pending export, so `/api/events/{id}/assets/flyer/export` requests a new export on each call until one completes. Add a poll or resume using the export job ID. Verify: a mocked test where a second export call polls the same job. Source: 03 context handoff (`d5ce546`).
- [ ] **A12 — Pitch assets.** `docs/PRESENTATION.md`: a 2-minute script that follows the final demo, plus the disclosure slide. Add `assets/**` for Canva deck exports.

## 4. Critical path

```text
A1 (Dockerfile PORT) ─┬─> M1 Render answers ─┬─> M2 Vercel BACKEND_ORIGIN ─> A15 deep link usable
                      │                      ├─> M3 Google redirect ─> M5 organizer connects Google
                      │                      └─> A4/M4 connector → Render ─> M5 Go token
A5, A6, A2 ───────────┴──────────────────────────────────────────────┐
M6 Canva ─> A7 ─> A8 ────────────────────────────────────────────────┤
A9/A16 UI for flyer + inclusion ─────────────────────────────────────┤
M7 Grammarly ────────────────────────────────────────────────────────┴─> M8 live rehearsal ─> M10 Devpost video + submit (8 PM PT)
```

If time runs short, cut in this order. Each cut must be stated honestly in the demo and on Devpost:

1. Canva revision on change (A8): show the stale flag instead.
2. Inclusion fact editing (A17).
3. Reply classification: Calendar RSVP statuses only.

Never cut: live Go writing plus a provider receipt, organizer approval before sending, and the same-ID Calendar update.
