# Contributing

The approved product is the event organizer website in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). Before work read [AGENTS.md](AGENTS.md), the global context, and all four member contexts linked in [the task plan](docs/TEAM_TASKS.md). Implement your assigned scope during the authorized build period. Update only your own personal context; Member 2 coordinates agreed global contracts. Use the four member roles to avoid overlapping edits.

## Pick up a task

Create an issue using the task template, agree its scope, and assign one owner. Check for overlapping work before editing shared files.

Start from an up-to-date `main`:

```sh
git switch main
git pull --ff-only origin main
git switch -c feature/short-task-name
```

Use `fix/` for fixes and `docs/` for documentation. Agent-created branches use `codex/`.

## Share a change

Keep the change focused on its issue. Review the diff before committing and add only the intended files:

```sh
git status
git diff
git add path/to/changed-file
git commit -m "Describe the change"
git push -u origin HEAD
```

Open a PR into `main`, link the issue, describe the behavior, and record how it was checked. Use a draft PR for unfinished work. Request a teammate review and resolve feedback before merging; squash merging keeps task history compact.

If your branch falls behind `main`, commit your work, fetch the latest changes, and merge `origin/main` into your branch. Coordinate conflicts with the affected teammate and avoid force-pushing a shared branch.

After merging, update your local `main` and remove the merged branch when it is no longer needed.

## Configuration and validation

Keep credentials in local environment files. Commit only placeholder configuration such as `.env.example`; the repository is public. Document any required environment variables when implementation begins.

Use the setup and check commands in the [README](README.md). Each PR must record the checks actually run and any checks blocked by missing credentials, services, or model files. A passing local scaffold check does not establish a working Superhuman Go installation or a deployed model.

For frontend/backend integration, follow [the Live Share workflow](docs/TEAM_WORKFLOW.md). The host commits changes from the shared checkout to the agreed feature branch, then opens a PR.
