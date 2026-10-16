# Shared project context

Last reviewed: 2026-10-16 (America/Los_Angeles).

This file carries agreed project knowledge between teammates, devices, and agents. It is a curated handoff, not a chat transcript. Read it before starting a task and before handing work to another owner. Follow [AGENTS.md](AGENTS.md) for the update rules.

## Goal and current phase

Build a working prototype for [MTC x Grammarly: Agents in Action](https://mtc-x-grammarly.devpost.com/) with Superhuman Go or Grammarly agents central to the user experience. See [the event brief](docs/HACKATHON.md) for the rubric and submission requirements.

The reusable scaffold is implemented and published. The product idea, primary track, and product-specific agent behavior are **not selected**. Brainstorming and recommendations are proposals until the team explicitly accepts them. Do not begin product implementation by assuming an idea was chosen.

## Accepted decisions

| ID | Decision | Reason / source |
| --- | --- | --- |
| D001 | Use React with TypeScript/TSX for the frontend and Python FastAPI for the backend. | Team lead's scaffold instructions, 2026-10-16; implemented in `frontend/` and `backend/`. |
| D002 | Expose Python tools to Superhuman Go through an authenticated Streamable HTTP MCP connector using the official Packs SDK. | Supported integration documented in [Superhuman setup](docs/SUPERHUMAN.md); do not assume a general Go inference API. |
| D003 | Divide development into backend, frontend, and documentation/Canva/presentation roles. Coordinate root configuration and shared interfaces through the task lead. | Team lead's three-agent workflow; ownership is in [AGENTS.md](AGENTS.md). |
| D004 | Keep CPU VPS deployment and Python/C++ ONNX inference optional. Choose training and model integration after the use case; measure before claiming an optimization. | Team lead's conditional deployment/model instructions; [architecture](docs/ARCHITECTURE.md) and [deployment](docs/DEPLOYMENT.md). |
| D005 | Use GitHub for shared source/tasks and VS Code Live Share for pairing on frontend/backend integration. | Team lead's collaboration instructions; [workflow](docs/TEAM_WORKFLOW.md). |
| D006 | Keep shared decisions and material handoffs in this tracked file. Every agent reads it before work and updates it when project knowledge changes. | Team lead's shared-context request, 2026-10-16. |

## Current implementation and contracts

- React development server: port `5173`; it proxies `/api` to Python on `8000`. Use `npm run dev:frontend` and `npm run dev:backend` after [README setup](README.md).
- `GET /api/health` returns `{"status":"ok","service":"backend"}`.
- `GET /api/status` returns `superhuman: {transport, configured, verified, endpoint}` and `model: {configured, runtime}`. Exact semantics and examples belong in [the architecture](docs/ARCHITECTURE.md) and [backend README](backend/README.md).
- `/mcp` requires a server-side bearer token and exposes `workspace_status` and `count_text`. These are readiness/protocol utilities, not the final AI product.
- Connector configuration uses a public example endpoint until a real HTTPS host is supplied. No external Superhuman installation has been verified; `verified` remains false.
- Optional CPU ONNX inference exists in Python and as an independent C++ smoke runner. No trained model or product inference endpoint is included.
- Docker Compose routes the frontend, `/api`, and `/mcp` through Caddy. No public VPS has been provisioned or deployed by this project setup.

## Verification evidence

These are recorded results from the scaffold handoff, not a claim that every future revision passes:

- Scaffold revision `78d5477`: [GitHub Actions](https://github.com/Josh-Roe/SuperhumanGo_HackProj/actions/runs/38876793067) passed frontend/backend checks, connector validation in the Linux Pack sandbox, Compose validation, both Docker builds, and a container-stack HTTP smoke test.
- Local scaffold validation reported 37 backend tests and 3 frontend tests passing. The backend suite included an optional ONNX Identity test fixture; the base CI environment skipped that optional ML test.
- A C++ ONNX CPU Identity smoke test succeeded during scaffold setup. This establishes a working runtime boundary, not model quality or a speed improvement.
- Frontend browser checks covered desktop/mobile layout and real API failure/recovery during scaffold setup.

When changing behavior, record the checks run for that revision in the handoff or linked PR. Do not copy these historical results as evidence for a later change.

## Open questions and external setup

- Which problem, primary track, intended user, and single demo workflow should the team choose?
- What product tools and external APIs are needed, and what is the agreed request/response contract?
- Teammates' GitHub usernames and collaborator invitations are pending; see [the roster](TEAM.md).
- A public domain/VPS and account-side Superhuman connector activation are pending. Configure real secrets locally; never record their values here.
- No training framework, model, dataset, or model-performance target has been selected.
- The published event date is October 16, 2026, with submissions at 8 PM Pacific. Confirm organizer communications because the initial description said “tomorrow.”

## Latest handoffs by role

Each owner maintains their own entry to reduce edit conflicts. Link to canonical docs and issues instead of copying them.

### Backend

- State: FastAPI, authenticated MCP tools, provider-neutral outbound JSON client, optional Python ONNX boundary, and C++ runner are implemented.
- Next: After idea selection, agree one product tool/API contract with frontend and implement it with meaningful tests.
- Evidence / limitations: [Backend guide](backend/README.md), [C++ guide](inference/README.md), and scaffold verification above; live Go and a trained model remain unverified/unconfigured.

### Frontend

- State: React/TSX starter reads real service status, handles errors/retry, and has responsive layout and a production image.
- Next: Build the agreed product's input → tool result → user action flow after the backend contract is accepted.
- Evidence / limitations: [Frontend guide](frontend/README.md) and scaffold verification above; starter status cards are not a product demo.

### Documentation, Canva, and presentation

- State: Architecture, team workflow, deployment/integration guides, submission checklist, and a two-minute pitch/Canva handoff template exist.
- Next: After idea selection, capture the problem, intended user, agent contribution, demo script, and evidence needed for the pitch.
- Evidence / limitations: [Presentation guide](docs/PRESENTATION.md); no product-specific deck or external submission has been created.

### Shared coordination

- State: This context file and the required agent read/update procedure are established at the team lead's request.
- Next owner / action: Team lead selects an idea after reviewing proposals. Keep proposals separate from accepted decisions.
- Checks for this documentation change: Local links and Git whitespace validation; application behavior is unchanged. The commit containing this entry is the evidence for the context setup.

## Entry formats

For a new accepted decision: `ID | decision | rationale | date | source (user instruction / issue / PR / commit)`. If replacing a decision, mark the old entry superseded and link its replacement.

For a material handoff: `date | owner / role | branch / commit / issue | completed outcome | contract or config changes | checks and evidence | blocker | next owner and action`. Omit fields that do not apply; never invent an assignee or successful check.
