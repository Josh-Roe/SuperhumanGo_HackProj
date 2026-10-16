# Organizer persistence and setup

Member 2 supplies the API/repositories; Member 3 registers them in `main.py` before its catch-all MCP mount. The default scaffold does not automatically enable these factories.

The hosted development project is `qkfebdbwrmpisejnazud`. The migration filenames match the actual hosted migration history. The first migration is recovered verbatim from that history; later migrations add task/event services and harden the initial schema. Use all migrations in order on a new project. Never use a remote `db reset` on the connected project.

## Server configuration

Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` for session validation and user-scoped REST access. No service-role key is needed for manual event/task CRUD. The ignored local `backend/.env` has the connected project's public configuration only.

For Go connector resolution and provider workers, configure `SUPABASE_SERVICE_ROLE_KEY` through server secret management. Configure `CREDENTIAL_ENCRYPTION_KEY` as a Fernet key for encrypted OAuth/Canva continuation secrets. Generate it once on the server using the command in `backend/.env.example`, protect it, and retain it across restarts. Losing the key makes existing ciphertext unreadable. No secret values are committed.

Google OAuth additionally requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`. Member 3 owns the OAuth callback and live account grants. `WORKFLOW_DEV_MODE=0` is forced in Compose; the in-memory development store is not multiuser persistence.

## Registration handoff

```python
from hackathon_backend.api import create_router
from hackathon_backend.api.dependencies import create_tool_dependencies, task_repository

# In Member 3's create_app composition, before app.mount("/", mcp_app):
app.include_router(create_router(settings))

# Pass to the existing create_app(events=...) parameter when server credentials are available:
events = create_tool_dependencies(settings)
```

`events.store` implements `WorkflowStore`; `events.principals` resolves hashed, expiring, revocable organizer tokens. Google distribution/RSVP adapters are attached only when their configuration is complete. Configuration is not evidence of a live provider connection.

For new MCP task/event creation tools, resolve the connector token using Member 3's principal helper first, then call `task_repository(settings, principal).create_task(TaskInput(...), idempotency_key)` or `create_event(EventInput(...), idempotency_key)`. Editing uses `TaskUpdate`/`EventUpdate` with `expected_revision`. Never expose `owner_id` as a tool argument. Go tool registration and a real Go session remain Member 3's work; these repository factories do not register task tools themselves. Manual REST and MCP use the same transactional RPCs.

Exact request/response schemas can be exported without credentials:

```sh
uv run --project backend --frozen python -m hackathon_backend.api.schema
```

REST uses `Authorization: Bearer <Supabase access token>`. `POST /api/events` and `POST /api/tasks` require `Idempotency-Key`. Creation retries with an identical normalized body return the original snapshot. Reusing a key for different input returns `idempotency_conflict`. PUT uses full editable fields plus `expected_revision`; inaccessible IDs return 404, stale revisions return 409. Readiness/public configuration is `/api/config`; only the publishable key is returned. Frontend sessions and token refresh belong to Member 1.

`POST /api/connectors` returns a personal Go token once. Store it in Go's connector configuration, not event prose. Listing omits hashes/tokens; DELETE revokes it. This is a bearer-token handoff, not an implemented OAuth authorization server for Go. Verify that Go's actual connector supports it; otherwise Member 3 must supply the appropriate OAuth bridge.

## Reviews, approvals and retries

`POST /api/events/{id}/prepare` queues one idempotent `awaiting_go` work batch per revision. MCP content writes require server privileges and remain `needs_review`. Browser users cannot claim `producer=superhuman_go`. `POST /api/content/{id}/review` approves unchanged content or creates a new `producer=organizer` edit with provenance. `POST /api/events/{id}/approvals` binds an organizer action to the exact current invitation/change-content ID. It does not send anything. Only Member 3's approved distribution executor performs Google writes.

Generation claims and provider attempts are atomic in Postgres. Concurrent execution fails with `operation_in_progress`. Completed receipts cannot change. An uncertain Gmail create/send is blocked from retry and from event revision changes until server-side provider read-back resolves it. `SupabaseWorkflowStore.reconcile_operation(owner,key,attempt,outcome,receipt)` accepts only `succeeded` or `not_applied` with nonempty provider evidence, requires the server client, and is not a public approval tool. Never infer `not_applied` from a missing draft alone. A process crash leaving an operation running requires the same reconciliation; there is no automatic lease takeover for external effects.

Member 3 must avoid superseding same-revision work in `enqueue_preparation`: the repository deduplicates work by owner/event/revision/batch. The implemented REST prepare route already preserves an existing same-revision batch. Saving multiple distinct Go outputs retains their history; a new event revision supersedes old outputs/jobs/pointers.

## Private storage and credentials

`event-assets` is private, max 10 MB per HTML/PNG object. Paths are `{owner}/events/{event}/r{revision}/{kind}/{sha256}.html|png`; insert policy checks the owner, event and canonical revision. User UPDATE is denied. `SupabaseAssetStorage` implements Member 4's interface, verifies bytes/hash on duplicate upload, and publishes the current pointer with revision CAS. A failed CAS leaves an orphan object, never a current pointer. Cleanup is deferred.

Authorized current links resolve through `/api/events/{id}/artifacts/{kind}/current`, which returns revision metadata and a 120-second signed URL. History is organizer-only. No public event page/link policy is implemented yet; old delivered files remain immutable snapshots. `SupabaseAttachmentSource` loads only reviewed artifacts for the exact revision and verifies their bytes before attaching them. Actual file upload/signing is mocked locally; live checks exercise Storage RLS with rollback-only metadata fixtures.

`SupabaseCredentialVault` encrypts refresh tokens and generic continuation state using authenticated owner/provider envelopes. `provider_secrets` has no browser grants; no raw secrets enter API DTOs. This generic secret boundary is available for Member 3's Canva job coordinator; Canva transaction claims and preview-approval registration still require that coordinator's handoff.

## Verification

```sh
uv sync --project backend --frozen --extra dev
uv run --project backend --frozen ruff check backend
uv run --project backend --frozen pytest backend/tests -q
supabase start
supabase db reset --local --no-seed
psql 'postgresql://postgres:postgres@127.0.0.1:54322/postgres' --set ON_ERROR_STOP=1 --file supabase/tests/organizer_isolation.sql
```

The SQL checks create synthetic users/records/Storage metadata inside a transaction and roll everything back. They cover owner isolation, validation, event/task CAS/history, duplicate creation, work/provider claims, content provenance, approvals, uncertain-effect reconciliation, private RSVP data and private Storage policies. They are not a live browser login, file upload, Go run or Google/Canva operation. CI replays migrations on a fresh local Supabase stack; the database job needs Docker. No deployment or real invitations are part of these checks.
