# Member 2 context: backend, Supabase, integration lead

Owner: Member 2 (human name/GitHub pending). Updated 2026-10-16. Status: **assigned; product implementation not started by this handoff**.

Read [global context](../../PROJECT_CONTEXT.md), [AGENTS](../../AGENTS.md), [all four member contexts](../TEAM_TASKS.md), and [contract](../INTEGRATION_CONTRACT.md) before work. Write only this personal context; you also coordinate canonical global docs/contracts. [Copy-ready prompt](../prompts/02_BACKEND_SUPABASE.md).

## Scope

Own Python event domain/API/auth/repositories, `supabase/**` schema/migrations/RLS/Storage setup, shared backend dependencies/config, root tooling/CI/VPS, and canonical architecture/contracts. Member 3 owns `main.py` composition and Google/Go workflows; Member 4 owns Canva/inclusion/assets services. Integrate their factories through explicit handoffs.

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

- Agreed from user: Python, Supabase data, Gemini/Go API integration, VPS path. No new training/inference work is needed for the MVP.
- Proposed: `docs/INTEGRATION_CONTRACT.md` is the initial contract to freeze, not an existing product API.
- Verification: planning links/whitespace are checked by the task lead; product data/auth behavior is not implemented or verified.
- Blockers: Supabase project/account configuration, four owners' contract agreement, public domain/provider credentials.
- Next action: read all contexts, freeze contract v0, and publish owner-scoped auth/repository interfaces here first.

## Update format

`Date | branch/commit/PR | status | decision/source | schema/API/env changes | checks/evidence | blocker | next owner/action`. Incorporate agreed global decisions into canonical docs; never edit another personal context or copy their unverified claims as successes.
