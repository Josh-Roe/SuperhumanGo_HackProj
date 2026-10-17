# Member 2 context: backend, Supabase, integration lead

Owner: Member 2 (this checkout). Updated 2026-10-16. Branch: `codex/member-2-backend-supabase`.
Status: **backend deployed to Render; live public health/config and unauthenticated route protection pass; authenticated persistence and real provider proof remain pending**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context; you also coordinate canonical global docs/contracts. [Copy-ready prompt](../prompts/02_BACKEND_SUPABASE.md).

## Scope

**2026-10-16 | implemented/tested | Canva deployment integration:** merged main `951f50a` (PR #9) into Member 2; retained legacy revision inclusion at `/inclusion/revision`, new UI facts at `/inclusion`, renamed A10's colliding RPC to `organizer_save_inclusion_facts` and applied canonical migration `20261017020000`. All five hosted rollback SQL suites pass, including approval replay identity and Canva lease/privacy checks; frontend 70 tests/lint/build and backend Ruff pass. Canva env names verified present without reading secrets; native entrypoint pins one worker. PR #9's verified MCP metadata supersedes the earlier endpoint proposal below. Deploy and real organizer consent remain pending.

Own Python event domain/API/auth/repositories, `supabase/**` schema/migrations/RLS/Storage setup, shared backend dependencies/config, root tooling/CI/VPS, and canonical architecture/contracts. Member 3 owns `main.py` composition and Google/Go workflows; Member 4 owns Canva/inclusion/assets services. Integrate their factories through explicit handoffs.

**2026-10-16 | implemented/tested | User 2 deployment integration:** merged team main `e265193`, retaining native Render hosting, User 1's Docker PORT/hostname changes, dashboard APP_URL and all peer changes; backend 343 passed / 1 optional ML skipped, uncached Ruff passes. No OAuth grants or provider sends performed.

**2026-10-16 | tested live | User 2 M1/M2/M11/A2:** Render `8d9418f` health 200/MCP 401/Google status 401; Vercel health/config 200 after user saved vars; WORKFLOW_DEV_MODE removed and redeploy `dep-db9d61vbtjjs73b9h4qg` live. Gemini/Notion exact constraints reject inserts and roll back. Two synthetic Auth organizers prove hosted MCP create/list/update plus REST share ID/revisions, idempotency, stale-write rejection and cross-owner isolation; cleanup leaves zero test users/events/tokens and removes sessions/revisions/request keys/local credential file. A11 jobs applied as hosted `20261017014208` from `c6f7d50`, lease/privacy rollback SQL passes, security advisor clean; migration-history alignment remains. A10 `20261017020000` blocked on its duplicate four-argument `organizer_save_inclusion` signature and conflicting deployed `/inclusion` contract; User 1 L2 needs compatibility patch before application. Docs A3 remain last; no prose rewrite while coding is incomplete, no provider sends or secret reads/changes.

**2026-10-16 | tested | migration history reconciliation:** M11/A11 history versions now match canonical checked-in `20261017010000`/`20261017030000`, preserving their applied SQL/statements and all data; no duplicate DDL. Copied exact A11 migration from main and added the hosted-passing lease/privacy SQL regression to CI. Latest main `9299ef6` reports an older-fork Vercel deployment despite working proxy/env values; preserve User 1's canonical-repo deployment blocker and new M12 Google Auth setup task. A10/L2 compatibility remains the next migration gate.

**2026-10-16 | proposed handoff | Canva account setup:** official Canva quickstart now uses Outside Canva → Configuration → Canva MCP for portal-created clients, endpoint `https://api.canva.com/connect/v1/mcp`; main still targets the waitlist endpoint `https://mcp.canva.com/mcp`. L3/Member 4 must reconcile that host and verify live discovery after OAuth deployment. Supabase Google login uses the separate `https://qkfebdbwrmpisejnazud.supabase.co/auth/v1/callback`, while Google provider tools keep the existing Render callback; user receives direct dashboard setup steps, with secrets entered only at their destinations.

## Live Render activation — 2026-10-16

**2026-10-16 | proposed/blocked | Canva deployment handoff:** user requested server-only `CANVA_CLIENT_ID`, `CANVA_CLIENT_SECRET`, `CANVA_REDIRECT_URI=https://superhuman-go-event-backend.onrender.com/api/canva/callback`, `APP_URL=https://mtcxhackathon1.vercel.app`, preserving existing Supabase/encryption credentials and redeploying with one worker after OAuth merge. Main `2581ee3` has no Canva OAuth route/settings or open OAuth PR; live callback returns 404, health 200, Render has one instance. Latest master plan assigns OAuth/shared code to User 1; Member 2 handles deployment. Member 4 account email supplied privately for a workspace invite; browser is signed out and connector has no invitation operation, so no invite/settings change occurred. Workspace Hobby plans cannot invite members (Render team-members docs); workspace tier itself is unverified. Existing credentials remain unchanged. Next: signed-in workspace admin invites if the plan permits, or owner enters Canva credentials directly; apply configuration and deploy only after OAuth merge.

**Tested live:** after the user saved the service-role credential directly in Render,
deployment `dep-db9cldijnfac73bptnog` of `5d1595a` reports `live`. Application startup
and MCP session-manager startup completed. HTTPS `/api/health` returns 200 with
`status=ok`; `/api/config` returns 200 with `configured=true` and only public Supabase
configuration. Anonymous `/api/events`, `/api/tasks` and `/mcp` return 401. Stable
backend: https://superhuman-go-event-backend.onrender.com; MCP path: `/mcp`.
This supersedes earlier activation/missing-service-key blockers below. No credential
was read back or copied into chat/Git. These checks do not establish authenticated
CRUD/Storage, provider grants, or a real Go/Canva/Google rehearsal.

**Next handoff:** Vercel server `BACKEND_ORIGIN` uses that backend origin; public
`VITE_PUBLIC_MCP_URL` uses its `/mcp` URL. Connect an organizer session and scoped
Go connector, then validate saved IDs/revisions and Storage before provider delivery.
Fetched main through `96658c8` and read updated peer contexts; that newer main is
not part of this deployed revision. This check changes only this personal context.

## Latest integration after Render connection — 2026-10-16

**Implemented:** merged new main `0d9ebf1`, including Member 3 composition `d5ce546`.
REST, authenticated create/update event/task MCP tools, Google callback and Member 4
asset/preview routes are now registered. This supersedes the older registration blocker
below. No peer-owned source was hand-edited. Core admin RPC tenancy is acceptable:
the principal supplies owner_id, invoker RPCs lock/filter the actual event/task by owner,
and cross-owner linked records are rejected even when the worker uses service role.

**Implemented/tested:** REST execution reuses Go's exact middleware service instance;
Member 3 asset-policy registration preserves pinned immutable preflight MIME bytes.
Google reconnect through a different vault instance now invalidates only that owner's
same-process access-token cache (weak listeners; one-instance Render path). Docker
startup honors PORT/proxy headers; Docker context excludes all secret `.env.*` files
and tests. Native readiness test covers the real Member 3 application composition.

**Applied:** upstream removal of Gemini/Notion kinds from `0d9ebf1`, hosted migration
`20261017005831`; filename mirrors actual remote history. Existing data was empty;
no producer/content rows were deleted or relabeled. New prose remains Go/organizer only.

**Activation:** browser dashboard redirects to Supabase sign-in; no service-role key
was accessible there. Render's encryption key is configured; add only the missing
SUPABASE_SERVICE_ROLE_KEY to the existing service, then redeploy this integration
branch. The native registration blocker is resolved by this merge. No credentials were
copied into chat/Git; no real invitations/provider assets were created in this continuation.
The service remains reserved at https://superhuman-go-event-backend.onrender.com.

**Validation:** combined backend **329 passed / 1 optional ML skipped**, uncached Ruff
and whitespace checks pass; frontend **51 tests**/lint/build pass. The real application
composition passes configuration readiness with synthetic server settings (no network
grant claimed). All three rollback SQL suites pass after the scope migration; security
advisor still has no findings. Earlier PR head `944558a` finished both CI jobs green;
this new integration receives another run before promotion.

## Continued Member 2 delivery — 2026-10-16

**User | agreed:** finish Member 2's remaining responsibilities, keep working through
role handoffs, automatically commit/push finished work. A VPS is optional; user asked
about free hosting. A stable Render Free service is now created; app activation is pending.

**Integrated baseline:** fast-forwarded the clean branch from `4ec2367` to merged
main `1752141`, preserving peer work. PR #3 is merged; its draft descriptions below
are historical. Read new Member 1 live-adapter PR #6 and accepted its canonical
CRUD/content/approval mapping, then merged its green branch (`de4e708`) into this
integration branch (`91b021a`). No peer-owned source was hand-edited.

**Implemented | exact handoff:** [BACKEND_API.md](../BACKEND_API.md), OpenAPI v0.3
(24 paths, 42 components): private workspace/work/binding/approval reads, retry-safe
approval recovery, distribution preview/execute using existing approval, exact export
review, and Member 4's typed private inclusion read/save/report. Inclusion saves advance
the canonical revision, invalidating old assets/prose/jobs/approvals. New consumer
mapping still needs 1/3 acceptance; existing endpoints stay compatible.

**Implemented | attachment safety:** production factory composes `PersistentDistributor`
with Member 4's strict `RevisionedAttachmentSource` over scoped Supabase reads. Require
both current reviewed PNG/document, validate type/path/source/revision/hash/size, and
pin bounded immutable bytes before Calendar invitations. Concurrent organizers cannot
mix MIME bytes; missing/corrupt assets block all provider writes. Retries reuse receipts.

**Tested live SQL:** migrations `20261017003828` (export review) and `20261017004313`
(approval recovery/private facts) applied to project `qkfebdbwrmpisejnazud`. Rollback
tests pass for exact hash/revision/source review, duplicate-free approval recovery,
private sourced inputs, changed-fact revision invalidation, foreign/anonymous denial
and prior isolation suite. Initial SQL syntax/fixture errors were corrected before
passing runs; test data rolled back. Security advisor has no findings; performance
advisor only unused-index INFO ([reference](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index)).
SQL/metadata tests are not actual file-upload/provider-send evidence.

**Prepared deployment:** `render.yaml`, native `api.serve`, read-only `api.readiness`,
and [setup/migration guide](../DEPLOYMENT.md). Supabase remains in place; no Docker/VPS
required. Native startup refuses absent/hidden REST registration, absent/different
persistent MCP dependencies, missing/invalid secrets or dev mode. Render Free sleeps
after 15 idle minutes; an infinite calculation cannot prevent it. User confirmed
workspace `Grammarly Hackathon` and the Free service; no paid compute was selected.

**Tested locally:** backend **284 passed / 1 optional ML skipped**, uncached Ruff
and diff whitespace pass; merged PR #6 frontend **51 tests**, lint/build pass.
Exact response schemas export successfully. All three rollback SQL suites passed
on hosted Supabase; a count check after the first two showed zero events/tasks,
export reviews and synthetic users. CI now replays every `supabase/tests/*.sql`.
Current CLI readiness correctly fails the unregistered production composition.
Render YAML parses with Free/native runtime and auto-deploy off. [CI run
38988028603](https://github.com/Josh-Roe/SuperhumanGo_HackProj/actions/runs/38988028603)
passed both checks and database jobs for implementation `8b2a38a`, including fresh
migration replay, all three SQL suites, Docker builds and container smoke tests.

**User requested an actual stable backend address | created:** connected Render;
confirmed workspace `tea-db9cb3u7bikc73fgplq0` (`Grammarly Hackathon`). Created
`srv-db9ccb7btjjs73b6pv50`, Free/Oregon, branch `codex/member-2-backend-supabase`,
auto-deploy off. Stable URL: https://superhuman-go-event-backend.onrender.com;
[dashboard](https://dashboard.render.com/web/srv-db9ccb7btjjs73b6pv50).
Initial deploy `dep-db9ccbnbtjjs73b6q080` failed during build because Render used
root Python 3.14 while the project requests 3.12 and disables managed downloads.
Added root `.python-version` to match the existing backend version. Application
startup still requires the registered persistent composition and server credentials;
the reserved URL is not a claim that event APIs are live.

**Live hosting follow-up:** native build for `28f9dc5` succeeded; Render selected
Python 3.12.15. Startup correctly failed the readiness gate for missing server keys
and Member 3 registration (`dep-db9cd4vavr4c73dhqdd0`, `update_failed`). Generated a
new encryption key, stored it in Render and mode-0600 Git-ignored `backend/.env.render`;
no secret value was printed or committed. Environment update queued its own deployment
(`dep-db9cdfbbc5jc73bmibmg`); no duplicate manual deploy was triggered. Preserve this
key for future encrypted provider grants. Service-role credentials remain absent.

**Exact next owners:** 3 registers `create_router(settings, events=deps)` before MCP
and passes the same `create_tool_dependencies(settings)` to `create_app`; adds typed
create/update MCP tools, persistent OAuth callbacks, and 4's preparation/Canva preview
approval/commit coordination. Durable Canva preview/job locks need the coordinator's
exact lifecycle contract; encrypted vault writes alone are not exclusive write locks.
1 adopts workspace/approval recovery/inclusion endpoints as needed. Export-byte review
is distinct from staged Canva transaction approval.

**Remaining Member 2 live blockers:** Supabase service-role credentials, authenticated
organizer fixture and provider grants are absent from this checkout. Render host and
encryption key are configured; application composition remains Member 3's handoff.
After 3's composition: deploy, configure Vercel `BACKEND_ORIGIN`, verify actual private
Storage upload/sign/read, restart persistence and cross-owner HTTP isolation, then
join the rehearsal. 3's live development-store Google/Go evidence is not proof of this
persistent path. Member 2 performed no real invitation/Calendar/Canva writes here.

## First deliverables

1. Publish exact v0 event, generation, artifact, operation, and RSVP schemas/examples. Obtain 1/3/4 agreement before schema-dependent work spreads.
2. Implement validated Supabase identity, event ownership/RLS, private RSVP/needs records, and protected Storage paths. Never rely on client-supplied owner IDs or expose service-role keys.
3. Implement canonical revisioned event CRUD and repository interfaces for content/assets, provider bindings, credentials, queue claims, approvals/idempotency, receipts, and RSVP provenance.
4. Make asynchronous and partial provider outcomes observable. Prepare VPS/env configuration and regression tests without starting real external sends.

## Dependencies and handoffs

- Need from 1: UI data/error needs and auth/session client behavior.
- Need from 3: exact Go tool, account identity/authorization, Google binding and operation requirements.
- Need from 4: Canva/inclusion/document metadata and secure Storage requirements.
- Supply to all: typed contracts, migrations/setup, environment names without values, repository methods, auth factories, and test fixtures. Ask 3 to register API routers in `main.py`.

## Decisions and progress

- **2026-10-16 | `codex/member-2-backend-supabase` | agreed (user):** Go is the primary task-creation interface through the website's custom MCP; manual website creation/editing remains supported. Python executes and persists; Go writes. Standalone tasks with optional event links are proposed pending terminology confirmation; existing event features remain intact.
- **2026-10-16 | implemented contract v0.2, cross-member acceptance pending:** public Pydantic request/response schemas live in `domain/models.py`; REST factory `api.create_router(settings)`; authenticated request scope `auth.identity.authenticate(settings, bearer)`; no client `owner_id`. REST uses a verified Supabase access token. Member 3's `PrincipalResolver` receives hashed, revocable per-organizer connector tokens; it never accepts the deployment MCP token. Task MCP handlers call the same `OrganizerRepository` methods as REST, never raw service-role queries. Export exact OpenAPI using `uv run --project backend --frozen python -m hackathon_backend.api.schema` (17 API paths).
- **Exact REST handoff (proposed):** `GET/POST /api/events`, `GET/PUT /api/events/{uuid}` (PUT full editable fields plus `expected_revision`); `GET/POST /api/tasks`, `GET/PUT /api/tasks/{uuid}` (PUT full editable fields plus `expected_revision`); create requires `Idempotency-Key` (1–128 printable characters). Event fields: `title`, `description`, `location`, offset-aware `starts_at/ends_at`, IANA `timezone`, HTTP(S) `links[]`, `organizer_contact`, `invitees[{email,display_name?}]`. Task fields: `title`, `description`, `status: todo|in_progress|done`, offset-aware optional `due_at`, optional event UUID. Server returns UUID, owner UUID, revision, timestamps. Lists are owner-scoped, newest first, bounded by `limit`/`offset`. Extra request fields are rejected; stale writes return HTTP 409 `revision_conflict`; inaccessible IDs return 404; invalid/absent session 401; missing configuration 503. Errors: `{detail:{code,message}}`.
- **Member 3 handoff (implemented against upstream `workflows/ports.py`, tested locally/mocked):** `repositories.workflow.SupabaseWorkflowStore` implements `WorkflowStore`; `auth.connectors.SupabasePrincipalResolver.resolve(token)` returns its stored owner only; `repositories.vault.SupabaseCredentialVault` implements encrypted Google refresh-token storage and generic Canva continuation-secret storage. `api.dependencies.create_tool_dependencies(settings)` assembles the existing `EventToolDeps`, single-writer Google adapters and reviewed exact-revision attachments. Work insert is atomic by owner/idempotency key, with current-revision check; a running claim is exclusive. Provider operations have atomic attempt transitions; unknown-effect failures require server read-back via `reconcile_operation` before retry, and receipts are immutable after success. Approval creation is an authenticated app action bound to revision and exact reviewed content; Go gets read-only approvals.
- **Member 4 handoff (implemented against upstream guide; Storage HTTP mocked, Storage SQL policy live-tested):** `repositories.assets.SupabaseAssetStorage` implements `assert_current`, immutable/hash-verified `put_if_absent`, revision-CAS `publish_current`; bucket `event-assets` is private; paths `{owner}/events/{event}/r{revision}/{kind}/{sha256}.html|png`, max 10 MB. Authorized current/history routes return metadata and short-lived signed links. No public RSVP/inclusion/credentials routes. OAuth and Canva continuation secrets use server encryption; keys stay in environment. `SupabaseAttachmentSource` validates bytes and reviewed/exact revision before returning attachments to Member 3. A real upload/signed URL round trip is still unverified.
- **Upstream integration:** merged Member 3 (`40304bb`), Member 4 (initial `3768f4e`, then `a45a0be`), and Member 1's published frontend branch/PR #2 into this integration branch. Other personal contexts are preserved verbatim from those branches. Draft [PR #3](https://github.com/Josh-Roe/SuperhumanGo_HackProj/pull/3) publishes this integration branch; no remote main merge. Canonical docs now incorporate only the user-agreed Go-first direction and Members 3/4's matching asset-prose kinds; frontend/standalone-task wire schemas still await consumer acceptance. This context and `supabase/README.md` contain the exact implementation handoff.

- **2026-10-16 | implemented, live SQL tested:** connected project `qkfebdbwrmpisejnazud`; versioned events/tasks, append-only snapshots, request-key deduplication, durable Go jobs, exact-content approvals, provider bindings, private RSVP observations, immutable receipts and private asset pointers. All migrations are committed with their actual hosted history versions. Tables use explicit grants/RLS; browser callers cannot forge Go producer labels or provider receipts. Supabase Auth is verified via `/auth/v1/user`, never unverified JWT decoding/user metadata. No global token authorizes organizer data.
- **2026-10-16 | tested locally:** Python 3.12 environment installed with the repository lock; backend **183 passed, 1 optional ML skipped**, Ruff passes, diff whitespace passes. New tests cover strict validation, Auth verification, owner-scoped repository requests, token hash/expiry/revocation filters, encrypted owner/provider credential envelopes, atomic error handling and private immutable uploads. A real Member 3 MCP handler → Member 2 repository flow passes with mocked Supabase HTTP. Browser login, live Go and provider operations are not established by these tests.
- **2026-10-16 | tested live on Supabase:** `supabase/tests/organizer_isolation.sql` passes with all synthetic users/rows/Storage metadata rolled back. Checks: two-account read/write isolation, private RSVP notes, anonymous denial, event/task validation and revision conflicts, idempotent creation, exclusive work/provider claims, browser Go-provenance denial, organizer edit provenance, exact/current approvals, immutable success receipts, uncertain Gmail reconciliation before retry, repeated Calendar-observation deduplication and private/immutable Storage policies. Follow-up query confirms zero synthetic users/events/tasks remain. Security advisor returns no findings. Performance advisor's missing owner FK index was fixed; unused indexes on this empty development database are expected.
- **2026-10-16 | implemented tooling:** Compose forwards server configuration and disables development workflows; encryption dependency is pinned/locked. CI has a fresh local Supabase migration replay and rollback SQL test job. Docker CLI/Compose config validation works locally, but the Docker daemon is stopped, so container build/local fresh-stack evidence awaits CI. No deployment or real invitations were performed.

- **2026-10-16 | main `e63354e` | proposed (A10, User 1 lane L2):** owner-scoped reads `GET /api/events/{id}/work?state=` (default open Go work), `GET /api/events/{id}/bindings` (calendar/gmail binding + `stale`), `GET /api/events/{id}/approvals?revision=`; `POST /approvals` now idempotent per revision/action/exact content (201 create, 200 replay, same id); `GET/PUT /api/events/{id}/inclusion` stores `InclusionInput` facts with `expected_version` CAS (409 `revision_conflict`) and returns the computed `InclusionReport` incl. `religious_observances`. A9 Canva preview read = existing `GET /assets` + `POST /assets/flyer/approve`. Needs migration `20261017020000_a10_inclusion_facts_and_idempotent_approvals.sql` (not applied). Consumers: Member 1 (A17), Member 4 (A9).
- **2026-10-16 | main `d54e6f6` | implemented, tested (mocked) (A10, User 1 lane L2):** `backend/tests/test_api_a10_reads.py` (12 HTTP-seam tests, Supabase + holiday feeds mocked). Live check waits on the migration.
- **2026-10-16 | main | agreed-by-analysis, test pending CI (A18, User 1 lane L2):** Go tools on the admin client are acceptable: the owner comes only from the connector-token lookup (`auth/connectors.resolve`), never from tool args, and `organizer_write_record`/`organizer_current`/`organizer_event_json` filter by `p_owner`; the task trigger re-checks event ownership. An RLS path would need per-user JWTs, which connector tokens do not have. Proof: `supabase/tests/go_tool_tenancy.sql` (two organizers via service_role), wired into CI.

## Exact next-owner actions and blockers

Latest integrated local validation: backend **183 passed / 1 optional ML skipped**, frontend **18 passed** plus lint/build, Superhuman Pack TypeScript/validation passed, Compose configuration passed. Docker daemon is stopped locally. [CI run 38982185599](https://github.com/Josh-Roe/SuperhumanGo_HackProj/actions/runs/38982185599) passed both jobs for backend commit `726a944`: full checks, both Docker builds, container smoke test, fresh local Supabase migration replay and rollback isolation SQL. Follow-up reply-job deduplication fix is locally tested and will receive a fresh PR run. These checks do not activate the frontend live adapter or register the new API factory in `main.py`.

1. **Member 3 registration:** in owned `main.py`, include `api.create_router(settings)` **before** the catch-all MCP mount and pass `api.dependencies.create_tool_dependencies(settings)` to `create_app(events=...)` when server configuration is present. Add task/event create/update MCP tools using `task_repository(settings, resolved_principal)` and strict `domain.models` inputs; do not expose owner IDs. Current merged tools read/prepare events but do not yet create tasks/events. Verify personal bearer-token support on the actual Go account or provide its OAuth bridge; hashed tokens are not proof of Go account compatibility.
2. **Member 3 queue/recovery integration:** `enqueue_preparation` currently supersedes same-revision jobs; change it to supersede only older revisions before using it with this deduplicating repository. REST `/prepare` already deduplicates correctly. Unknown Gmail creates/sends and crashed running operations remain blocked until real provider reconciliation; do not promise a blind retry. Canva transaction/job locking and preview-approval routes still require the coordinator's integration; generic encrypted continuation storage is available.
3. **Member 1 API mapping:** its proposed live gateway differs from this published REST contract: it expects `WorkspaceEvent` on detail/create/prepare, PATCH edits, client invitee IDs, and create without an idempotency header. This implementation returns canonical `EventRecord` on detail/create/PUT, `WorkItem` on prepare, separate review/content/approval/status endpoints, and requires `Idempotency-Key` on creation. Member 1 must map the adapter or agree a revised server read model before enabling live mode. Its latest user-approved shell skips initial login and uses isolated preview data; that does not authorize anonymous private-record access. Connect authenticated data via Settings/Profile in coordination with Member 1.
4. **Account/server blockers:** supply server-only `SUPABASE_SERVICE_ROLE_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, organizer OAuth grants, HTTPS host and Go installation. Public Supabase URL/publishable key are configured in ignored local `backend/.env`; no secret values are in Git. Manual REST CRUD uses the user's Supabase session and needs no service key; MCP principal resolution and provider workers do.
5. **Remaining proof:** frontend-to-real-session CRUD/review; actual Storage upload/signing; live Go task/event creation and saved prose; Grammarly client assistance; actual Canva/Google revisions and RSVP receipts. Public event links remain deferred pending an approved public schema. Preserve pre-existing-work disclosure and obtain organizer publish/update actions before any provider invitations.

## Update format

`Date | branch/commit/PR | status | decision/source | schema/API/env changes | checks/evidence | blocker | next owner/action`. Incorporate agreed global decisions into canonical docs; never edit another personal context or copy their unverified claims as successes.
