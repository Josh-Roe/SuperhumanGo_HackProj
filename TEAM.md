# Team coordination

## Roster

The hackathon overview requires a team of 2–4 people. Teammate usernames will be provided later; collaborator invitations and role assignments are pending.

| GitHub account | Repository role | Project responsibility |
| --- | --- | --- |
| [@Josh-Roe](https://github.com/Josh-Roe) | Owner | To be agreed |

## Working agreements

- Use GitHub Issues as the shared task list. Give each active task one owner, a small outcome, and a clear completion check.
- Before starting, assign yourself and comment `In progress`. If blocked, comment with the blocker and the help needed.
- Use an open issue for planned work, an open PR for review, and a closed issue for completed work. Link the PR with `Closes #<issue>` so merging closes the task.
- Coordinate shared-file changes before editing. Keep branches short and push work regularly so teammates can pick it up.
- Ask an available teammate to review a PR before merging. This is a team convention; branch protection is not configured by this setup.
- Record project decisions in the relevant issue and update the README with agreed setup instructions.

## Four development members

Each person sends one [assigned prompt](docs/TEAM_TASKS.md) to their own agent. All agents read every member's context but write only their own. Human names/usernames are still pending; these are role assignments, not claims about a named teammate.

| Member | Owns | Handoff |
| --- | --- | --- |
| 1: Frontend | `frontend/` | Login/event/review/distribution/update/RSVP screens and typed API needs |
| 2: Backend/Supabase and integration lead | Event API/domain/auth/repositories, `supabase/`, shared tooling/contracts/VPS | Auth/RLS, versioned data/Storage/queue, exact schemas and CI |
| 3: Superhuman Go/Google | Go connector/tools, Google adapters/workflows, `main.py` | Live Go writing/coordination, Gmail/Calendar changes, RSVP and provider receipts |
| 4: Canva/inclusion/presentation | Canva/inclusion/assets services and product/pitch assets | Flyer create/update/export, inclusion findings, Go-written documents and demo |

See [AGENTS.md](AGENTS.md) for exact module/test/context ownership and [the workflow](docs/TEAM_WORKFLOW.md) for pairing. Member 2 edits dependencies/config/contracts; Member 3 registers everyone's factories in `main.py`. Shared-file changes go through their owner.

## Decisions still open

The event-management idea and React/Python/Supabase/Go stack are selected. Website name, final primary track, human role assignments, account credentials, and live deployment/trigger configuration remain open. The existing optional ML/ONNX path is deferred behind the event workflow. No live product integration is implied by the scaffold.

## Adding teammates later

The repository owner can invite the supplied usernames under [Settings → Collaborators](https://github.com/Josh-Roe/SuperhumanGo_HackProj/settings/access). Add accepted teammates to the roster and agree responsibilities before dividing implementation work.
