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

## Development agents

Use three agents with clear ownership. These are development responsibilities, not the product's eventual agents or assignments to named teammates.

| Agent | Owns | Handoff |
| --- | --- | --- |
| Backend | `backend/`, `inference/` | API schemas, integration configuration, tests, model input/output contract |
| Frontend | `frontend/` | React UI, API client, loading/error states, browser validation |
| Documentation and presentation | `docs/`, team/contribution guides, Canva and pitch preparation | Accurate setup guide, screenshots, pitch script, submission evidence |

Coordinate changes to root tooling, CI, deployment, and the Superhuman connector before editing. See [the agent instructions](AGENTS.md) and [team workflow](docs/TEAM_WORKFLOW.md).

## Decisions still open

Project idea, primary track, named task owners, team communication channel, and demo/submission owner remain to be agreed. The stack is React with TypeScript, Python APIs/ML, and an optional CPU VPS and ONNX inference path. The scaffold supports those choices; no product idea, trained model, or live deployment is assumed.

## Adding teammates later

The repository owner can invite the supplied usernames under [Settings → Collaborators](https://github.com/Josh-Roe/SuperhumanGo_HackProj/settings/access). Add accepted teammates to the roster and agree responsibilities before dividing implementation work.
