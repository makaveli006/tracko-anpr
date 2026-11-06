# Git and GitHub rules

## Branches

- `main` — the released state. It only changes through a pull request from `development` on GitHub.
- `development` — the integration branch. All work lands here first.
- Work branches, always created from `development`:
  - `feature/<short-name>` for new functionality
  - `bug/<short-name>` for fixes
  - `docs/<short-name>` for documentation

## Workflow

The same steps apply to feature, bug and docs branches:

1. Update `development`, then create the work branch from it.
2. Do the work and commit on that branch.
3. When the implementation is finished, merge the branch into `development`.
4. Delete the work branch, locally and on GitHub if it was pushed.

Never commit work directly on `main`. Never start a work branch from `main`.

## Not allowed

- **Merging `development` into `main` locally.** That merge happens only as a pull request on GitHub. Afterwards, bring it down with `git pull` on `main`.
- **Deleting the local `main` or `development` branch**, including renaming either of them away.

## Enforcement

These two restrictions are enforced by git hooks in `.githooks/`, not by Claude Code hooks:

- `.githooks/reference-transaction` blocks deleting or renaming `main` and `development`, and blocks `development` reaching `main` locally by merge, fast-forward, reset or `git branch -f`.
- `.githooks/pre-merge-commit` stops a local merge of `development` into `main` before the merge commit is made.

Git does not turn on versioned hooks by itself. Each clone must run this once:

```bash
git config core.hooksPath .githooks
```

Do not work around the hooks: no `--no-verify`, no unsetting `core.hooksPath`, and no editing the hooks to let a blocked action through. If a hook blocks something, follow the workflow above instead.

The hooks only act on this machine's clone. They do not stop someone pushing to `main` on GitHub from another clone; that needs a branch protection rule in the GitHub repository settings.

## Handing over changes

Claude does not run `git add`, `git commit`, `git merge` or branch deletion itself. After every implementation or change, Claude gives the user the commands to run, one per line and in order, ready to copy:

```bash
git checkout development
git checkout -b feature/<short-name>      # or bug/<short-name>, docs/<short-name>
git add <the files that changed>
git commit -m "<commit message>"
git checkout development
git merge feature/<short-name>
git branch -d feature/<short-name>
```

Always fill in the real branch name, the real file paths and a real commit message; never leave placeholders. List the files explicitly rather than using `git add .`, unless every untracked and changed file belongs in the commit.

## Commit messages

- Do not add a `Co-Authored-By: Claude` line, or any other AI attribution line, to commit messages.
