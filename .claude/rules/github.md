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

## Claude runs the whole sequence

The user decided on 2026-11-06 that Claude always does the commit, merge and branch deletion itself, to save time. There is no hand-over of commands and no waiting for "U DO".

Before starting any implementation or change, Claude creates the work branch from `development`:

```bash
git checkout development
git checkout -b feature/<short-name>      # or bug/<short-name>, docs/<short-name>
```

When the work is done and verified, Claude runs these itself, in order, stopping at the first error:

```bash
git add .
git commit -m "<commit message>"
git checkout development
git merge feature/<short-name>
git branch -d feature/<short-name>
```

Then Claude reports what was committed and the state of `development`.

Rules for that sequence:

- **Check the branch first.** Before `git add .`, confirm the current branch is the work branch. If it is `development`, `main` or anything unexpected, stop and tell the user; do not commit.
- **Check what is being staged.** `git add .` stages everything, so `.gitignore` is the only thing keeping videos, model weights, secrets and generated files out. Look at `git status` before committing; if something large or secret would go in, fix `.gitignore` first.
- **Always `git add .`,** never a list of individual file paths.
- **Never `git push`.** The work stays local; the user pushes the day's collected work themselves at the end of the day.
- **Nothing beyond this sequence without being asked:** no amending or rewriting commits, no force operations, no work on `main`.

## Commit messages

- Do not add a `Co-Authored-By: Claude` line, or any other AI attribution line, to commit messages.
