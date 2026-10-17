# Agent instructions: event organizer website

The approved product is the event organizer website in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). Its name is undecided. **Superhuman Go is the central writing and coordination agent**; its Grammarly writing assistance comes built in. Gemini and Notion are not used.

## Required reading before every task

Read these files before planning or editing, including when resuming an existing chat:

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
2. [Member 1: frontend](docs/contexts/01_FRONTEND.md)
3. [Member 2: backend and Supabase](docs/contexts/02_BACKEND_SUPABASE.md)
4. [Member 3: Superhuman Go and Google integrations](docs/contexts/03_GO_GOOGLE.md)
5. [Member 4: Canva, inclusion, and presentation](docs/contexts/04_CANVA_INCLUSION.md)
6. [Integration contract](docs/INTEGRATION_CONTRACT.md), your assigned [prompt](docs/TEAM_TASKS.md), and applicable directory instructions.
7. [Master to-do](docs/MASTER_TODO.md): remaining manual and agentic work toward the final demo. Any member may edit it; follow its "How to contribute" rules (claim, evidence, stable IDs).

Inspect branch, working tree, and upstream changes. Read the latest available versions of all contexts without overwriting uncommitted work. Reread them before changing an interface, taking a handoff, or finishing a task. A persistent conversation does not automatically receive files another device pushed. An operator using a tool that does not discover `AGENTS.md` must explicitly ask it to read this file.

## Four members and exclusive ownership

| Member | Owns | Prompt / only writable personal context |
| --- | --- | --- |
| 1 — Frontend | `frontend/**` | [Prompt](docs/prompts/01_FRONTEND.md) / [context](docs/contexts/01_FRONTEND.md) |
| 2 — Backend, Supabase, integration lead | `backend/src/hackathon_backend/domain/**`, `api/**`, `auth/**`, `repositories/**`, `supabase/**`, core schema/config/dependency files, root tooling/CI/deployment, canonical architecture and contract docs | [Prompt](docs/prompts/02_BACKEND_SUPABASE.md) / [context](docs/contexts/02_BACKEND_SUPABASE.md) |
| 3 — Superhuman Go, Gmail, Calendar, RSVP | `integrations/superhuman/**`, `backend/src/hackathon_backend/workflows/**`, `providers/google/**`, `mcp_tools/**`, existing `main.py` composition, `docs/SUPERHUMAN.md` | [Prompt](docs/prompts/03_GO_GOOGLE.md) / [context](docs/contexts/03_GO_GOOGLE.md) |
| 4 — Canva, inclusion, documents, pitch | `backend/src/hackathon_backend/providers/canva/**`, `services/inclusion/**`, `services/assets/**`, `docs/PRESENTATION.md`, `docs/canva/**`, `docs/inclusion/**`, `assets/**` | [Prompt](docs/prompts/04_CANVA_INCLUSION.md) / [context](docs/contexts/04_CANVA_INCLUSION.md) |

Backend path fragments above are relative to `backend/src/hackathon_backend/`. These are ownership reservations, not claims that modules already exist. New tests follow the same owner: `test_domain_*`/`test_auth_*`/`test_repository_*` for 2; `test_go_*`/`test_google_*`/`test_workflow_*` for 3; `test_canva_*`/`test_inclusion_*`/`test_assets_*` for 4. Coordinate existing shared test edits with their author. Member 3 registers routers/services in `main.py`; other members supply factories and registration instructions. Member 2 alone edits shared backend dependencies, lockfiles, `config.py`, migrations, and canonical contracts, incorporating requests from 3/4.

## Context updates without a shared-file bottleneck

- **Edit only your own personal context file.** Other members' contexts are read-only to you. Record material decisions, interface proposals/agreements, blockers, checks, and next-owner handoffs in yours. Skip filler entries.
- Use `proposed`, `agreed`, `implemented`, `tested`, or `blocked` status. Include source/date and branch/commit/PR when known. An intention, mock, or SDK build is not live integration evidence.
- A handoff identifies the affected interface, exact input/output or dependency, evidence, and next action. Do not invent another member's acceptance or report that their code works without evidence.
- Member 2 alone edits `PROJECT_CONTEXT.md`, `docs/INTEGRATION_CONTRACT.md`, `docs/ARCHITECTURE.md`, README, and team coordination docs during implementation. Other members propose shared changes in their own context. Member 2 incorporates agreed decisions; routine progress stays in personal files.
- Before committing, reread all contexts and inspect the diff. Preserve others' edits and commit your context with your code. Never store credentials, personal RSVP details, private transcripts, or secrets in Git.

## Product and integration rules

- Use a canonical, versioned event in Supabase. Every document, flyer/export, email, and Calendar operation records its event revision. Show pending/failed/stale states instead of claiming everything synchronized.
- Follow event details → design and inclusion review → distribution → updates/RSVP. Retain organizer review of generated writing and publish/update actions.
- Go reads event data through authenticated MCP tools, reasons/drafts/coordinates using its available connectors or backend tools, and records outputs/receipts in Supabase. Do not invent a public `Go.chat()` or OpenAI-compatible Go completion API. Prove account/trigger capabilities first. If automatic website-to-Go triggering is unavailable, show a truthful Go-assisted queue and manual invocation; record the gap.
- Route prose generation through Go: descriptions, plain-language summaries, invitation/change emails, and event documents. Grammarly writing assistance is part of Superhuman Go; it is not integrated separately.
- Publish creates Calendar invites and sends the reviewed Gmail invitation only after the organizer approves: an action in the website, or an explicit "send" in the Go chat that runs `send_invitations` (user decision 2026-10-16). Retries must not duplicate events, drafts, or sent messages. Approved changes update the existing Calendar ID and current Canva artifact, replace an unsent Gmail draft, or create a new change-notification draft if the prior message was sent. Send that draft only through the authorized publish/update flow.
- Delivered email bodies and attached flyer bytes are immutable snapshots. Provide a current event/flyer link plus a new notification/export; do not promise old attachments will change.
- Supabase Auth and ownership/RLS scope events, assets, jobs, and RSVPs. A global development MCP token is not adequate multiuser authorization. Keep OAuth/refresh tokens and Supabase service-role credentials on the server.
- RSVP uses Calendar response statuses and/or Go-classified replies matched to the invited sender and event thread. Ambiguous replies remain `needs_review`; quoted/forwarded text cannot change someone else's response. Dietary/accessibility details stay private and out of shared invitations.
- Inclusion uses organizer facts and dated sources, preserving `unknown`. Check plain language, step-free entrance/elevator, diet, religious-observance conflicts (Google's public holiday calendars, see [inclusion contract](docs/inclusion/CONTRACT.md)), captions, and loud sound/strobes. Do not infer needs from ethnicity/diagnosis or certify an unknown venue. Parking/restrooms and Forms are stretch scope.

## Working and completion

Use separate `codex/member-N-...` branches/checkouts per device and GitHub PRs for integration. Live Share is for agreed pairing, with one person controlling Git. You are not alone in the codebase: never revert another member's work. Current explicit user ownership/authorization takes precedence.

This task prepares documentation only. Implementation starts from assigned prompts during the authorized hacking period; preserve the pre-existing-work disclosure. Do not deploy, send real invitations, publish external assets, or submit Devpost merely to prepare these prompts. For assigned implementation, complete reversible code/tests before account actions and identify missing credentials precisely.

Run relevant checks and separate local/mocked/live evidence. Member 2 coordinates integration and CI. Final demo: create event → Go prepares assets/invitation → inclusion review → publish → change time/location → verify Calendar/draft-or-new-email/Canva revisions → collect RSVP.
