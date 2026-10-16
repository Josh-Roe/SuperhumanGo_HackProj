# Contributing

Implementation starts after the team has agreed the project and given instructions. Until then, keep changes limited to repository setup and coordination.

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

No build, test, or CI commands are defined yet because the stack is undecided. Each PR should state the checks actually run; add shared validation commands to the README once the stack exists.
