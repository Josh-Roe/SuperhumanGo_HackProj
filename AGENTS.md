# Development agent instructions

The team uses three development agent roles. Select the relevant role for a task; use parallel agents when separate frontend, backend, and documentation work is useful. Small edits do not require starting all three agents.

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
