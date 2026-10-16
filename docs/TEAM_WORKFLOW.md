# Team workflow

GitHub holds the shared source of truth. Use Issues for tasks and PRs for changes. Live Share is for pairing and integration in one checkout; it does not replace commits or review.

## Divide the work

Start each task with one owner, a small outcome, and a completion check. Use the [four-member plan and prompts](TEAM_TASKS.md): 1 frontend; 2 backend/Supabase; 3 Superhuman Go/Google; 4 Canva/inclusion/presentation. Read the global context and all four personal contexts before work, but update only your own personal context. Member 2 coordinates shared contracts/dependencies/config; Member 3 owns `main.py` registration. Named teammates join [the roster](../TEAM.md) when usernames arrive.

Agree method, URL, payload, response, errors and sample before building. [The initial event contract](INTEGRATION_CONTRACT.md) is a planning baseline; Member 2 freezes exact schemas with the consumers. FastAPI `/docs` and `/openapi.json` describe only currently implemented endpoints. `/api/health` and `/api/status` remain scaffold endpoints; event features are assigned work, not already implemented.

Each handoff should include:

- Issue/PR and changed files.
- Contract changes and an example call or response.
- Checks run and their result.
- Environment variables or services needed, without secret values.
- Remaining blocker and the next owner.

## Pair frontend and backend with VS Code Live Share

1. Both teammates install VS Code's Live Share extension and sign in. The host opens this repository and switches to an agreed feature branch. Commit or stash unrelated work first.
2. Run `npm run dev:backend` and `npm run dev:frontend` in separate host terminals after completing the README setup. Confirm the frontend can reach the host's backend through the Vite `/api` proxy.
3. Start Live Share and send its invitation privately to the teammate. Confirm ownership before coediting; both participants are editing the host's files.
4. In Live Share's **Shared Servers**, choose **Share server**, enter `5173`, and name it `Frontend`. The guest opens the forwarded URL from Shared Servers. A different guest port may be chosen if `5173` is occupied. See [Microsoft's server-sharing guide](https://learn.microsoft.com/en-us/visualstudio/liveshare/use/share-server-visual-studio-code).
5. Exercise the status screen and browser network requests together. Share backend port `8000` only when direct API debugging is needed. Keep credentials and environment files excluded from sharing; do not paste tokens in shared terminals or chat. Prefer a read-only terminal when showing logs. See [Microsoft's Live Share security guidance](https://learn.microsoft.com/en-us/visualstudio/liveshare/reference/security).
6. Run the relevant checks. The host reviews and commits the combined diff, credits the pair in the PR, pushes the branch, and requests review. Record any API decisions in the issue.

Do not have both teammates run independent Git operations against the same Live Share checkout at the same time. A guest returning to their own clone should fetch the committed branch and resume there.

## Keep the demo ready

Merge small, verified PRs. Keep setup instructions current and distinguish local checks from external integration checks. Before the pitch, use the [presentation brief](PRESENTATION.md) and [hackathon checklist](HACKATHON.md). Record a fallback video using the actual implementation, with credentials and personal data removed.
