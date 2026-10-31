# Commit and PR guardrails

From the repository root, with Python 3.11+ and Git on PATH:

```powershell
python -m pip install -r requirements/dev.txt
python scripts/install_hooks.py
```

Each clone needs installation. The installer sets local `core.hooksPath` to
the absolute `.githooks` path in the installing checkout and refuses to replace
a different configured hooks directory. Keep that checkout available: linked
worktrees share these hooks, including when their branch has older hook files.
Use task branches `<type>/<lowercase-kebab-description>`, such as
`chore/repository-guardrails`. Allowed types: `feat`, `fix`, `chore`, `docs`,
`refactor`, `test`, `perf`, `build`, `ci`, `revert`. Hooks check the current branch
before commit and push, rejecting legacy personal names, `main`, and detached
HEAD. PR CI checks the source branch name. This is the repository convention,
not a universal Git standard; folder ownership is unchanged.

`pre-commit` checks the staged snapshot, rejecting private paths, unresolved
conflict markers, and whitespace errors. Unstaged fixes do not fix staged errors;
stage the corrected file again. Removing an accidentally tracked private file is
allowed. `.env.example` is allowed and must contain placeholders only.

`pre-push` checks all tracked index entries, imports `contracts`, and runs the
entire acceptance suite. Run the same command manually before opening a PR:

```powershell
python scripts/guardrails.py --all --tests
```

GitHub Actions repeats this check on PRs and pushes to team branches and main.
The PR template records behavior, contract changes, review ownership, and evidence.
To enforce checks before merge, a repository administrator must require
`Guardrails and acceptance tests` in the main branch ruleset. This setup does not
change GitHub branch protection or publish changes.

Local hooks can be bypassed; they are feedback, not an authorization boundary.
Push checks inspect the local index, not every historical commit being pushed.
CI checks the PR checkout. Path checks do not detect arbitrary secrets embedded
in source files. Ownership and business safety rules still require human review
and appropriate acceptance tests; these hooks do not implement agent safety logic.

CodeGraph is initialized locally. Its `.codegraph/` index stays untracked.

## Local files in worktrees

`docs/superpowers/` contains local specs and plans and stays ignored.
After installing hooks, use ordinary Git commands:

```powershell
git worktree add -b feat/order-tracking ../sea-openai-order-tracking main
```

The `post-checkout` hook copies all ignored files from the installing checkout
into the newly created worktree, including local specs, `.env`, data, databases,
virtual environments, and caches. It skips existing destination files and other
linked worktrees; it does not modify source files. This is a one-time copy, not
ongoing synchronization. Large ignored directories increase creation time, and
copied virtual environments may need recreation because they contain absolute paths.

Git does not invoke this hook for `git worktree add --no-checkout`.
To copy manually, run the source checkout's `scripts/sync_worktree_ignored.py`
using an absolute path while your current directory is the destination worktree.
Ordinary branch switches do not trigger copying. Existing tracked files are never
overwritten. The installer also adds local shared exclude rules for
`docs/superpowers/`, `.codegraph/`, and `.worktrees/` so these remain ignored
even in branches predating this configuration. Other ignore rules come from
each branch or your global Git configuration.
