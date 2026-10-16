# Development agent instructions

The team uses three development agent roles. Select the relevant role for a task; use parallel agents when separate frontend, backend, and documentation work is useful. Small edits do not require starting all three agents.

## Required shared-context workflow

Before starting any task:

1. Read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), then the docs and issue relevant to your task. Do not assume another agent's chat history is available or that a local memory is shared with teammates.
2. Inspect the current branch and working-tree state. Check whether the shared context and code have changed upstream; incorporate relevant updates without overwriting uncommitted work or another owner's edits. For an existing long-running session, reread the context before starting a new task or taking over a handoff.
3. Identify your scope, accepted decisions, open questions, and the current interface contract. Distinguish a proposal from a team-approved decision. Explicit current user instructions take precedence; record any resulting material decision.

During work and before the final handoff:

- Update `PROJECT_CONTEXT.md` when an important decision, interface/configuration change, blocker, corrected assumption, or ownership handoff would affect another agent's work. A task that introduces no material shared knowledge does not need a filler entry.
- Record the decision and rationale with its date and source (user instruction, issue, PR, or commit). Mark replaced decisions as superseded; do not silently remove their rationale or turn a suggestion into an accepted decision.
- Update your own role's latest handoff with the outcome, relevant branch/commit/issue, checks actually run, limitations/blockers, and next owner/action. Do not invent an assignee. Reconcile stale handoffs when a blocker is resolved.
- Link to canonical contracts, docs, and evidence instead of duplicating them. Keep the file concise; exclude raw transcripts, routine logs, credentials, private user history, and unsupported success claims.
- Reread the current context and diff before committing. Preserve other owners' entries and resolve context conflicts by keeping all compatible material decisions. Commit relevant context updates with the work they describe, and mention the context change in the handoff.

This file-based workflow applies across devices and agent tools. Agents that do not discover `AGENTS.md` automatically must be explicitly instructed by their operator to read it and `PROJECT_CONTEXT.md`. Shared Git files synchronize when fetched/pulled; they do not merge private conversation histories or push updates into a running agent's context automatically.

## Ownership

| Role | Primary files | Responsibility |
| --- | --- | --- |
| Backend | `backend/**`, `inference/**` | Python API, MCP tools, ML integrations, optional ONNX Python/C++ inference, backend tests |
| Frontend | `frontend/**` | React/TypeScript UI, API client, accessibility, responsive layout, frontend checks |
| Documentation, Canva, and presentation | `docs/**`, `TEAM.md`, `CONTRIBUTING.md` | Setup and architecture docs, pitch, demo script, Canva handoff, submission checklist |

The task lead coordinates root configuration, CI, `deploy/**`, the Superhuman SDK connector, and cross-cutting changes. Explicit ownership in the current task takes precedence over these defaults. Coordinate edits to shared files before starting. Other people and agents may be editing this checkout; preserve their changes.

## Scope and contracts

- The scaffold is approved. The product idea and track still need a team decision. Do not invent product requirements or represent placeholder flows as completed features.
- Keep React/TypeScript in `frontend/` and Python API/ML work in `backend/`. Treat `inference/` as an optional optimization path; measure correctness and CPU latency before preferring C++.
- Agree API changes with the other owner first: method, path, request/response schema, error behavior, and a sample response. Update consumers and documentation together.
- Keep API credentials and MCP bearer tokens on the server. Never expose secrets through `VITE_*`, browser assets, commits, screenshots, or demo recordings.
- Follow `docs/SUPERHUMAN.md` for the actual connector and authentication flow. Do not invent a general Superhuman Go inference API or SDK methods.
- Do not claim external integration, training, deployment, performance, or tests succeeded without evidence. Label unavailable credentials, model artifacts, and unrun checks clearly.

## Completion

Use a focused issue and branch for feature work. Run the relevant README checks, review the diff, and open a PR with the behavior and validation. Commit directly to `main` only when the user has requested it, as for the initial scaffold. Do not deploy, publish a Canva deck, invite teammates, or submit to Devpost without task authorization.

Hand off changed files, contract changes, checks run, missing configuration, and the next integration step. Keep the team workflow and presentation materials aligned with implemented behavior.
