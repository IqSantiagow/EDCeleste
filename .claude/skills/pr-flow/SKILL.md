---
name: pr-flow
description: Creates a PR, monitors the CI pipeline and Claude code review, manages fixes iteratively — from commit to merge-ready
---

Run the full PR cycle for the current branch. Execute the steps in order.

## Step 1 — Local check: lint and tests

Before committing, verify locally that the code is clean and the tests pass — this catches issues before they hit the CI pipeline:

```bash
ruff check
ruff format --diff
coverage run -m unittest discover
coverage report -m
```

If `ruff check` reports errors, fix them (`ruff check --fix` and `ruff format`). If any test fails, identify and fix the cause. Do not proceed to Step 2 until both lint and tests are clean.

## Step 2 — Check state

```bash
git status
git diff HEAD
```

Make sure that:
- The branch is `feature/*` or `fix/*` — not `main`
- There are changes to commit

## Step 3 — Commit

Create a commit with a specific description (what changed and why). Stage only files related to the current change — never `git add .` or `git add -A`.

**ABSOLUTE PROHIBITION:** No `Co-Authored-By:` or any other trailer. The commit message ends after the description, with no additional lines.

```bash
git add <specific files>
git commit -m "$(cat <<'EOF'
<commit title — what and why>
EOF
)"
```

## Step 4 — Push

```bash
git push -u origin HEAD
```

## Step 5 — Create PR (if it doesn't exist)

Check whether a PR already exists:
```bash
gh pr view 2>/dev/null && echo "PR EXISTS" || echo "NO PR"
```

If no PR exists, create one. Title ≤70 characters. NO Co-Authored-By in the body:

```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
- <what was changed>
- <why / what problem it solves>

## Test plan
- [ ] Lint and tests pass
- [ ] <specific steps to verify the change>
EOF
)"
```

Note the PR number — it will be needed to fetch comments.

## Step 6 — Monitor the pipeline

Wait for all checks to finish. Jobs run sequentially: `lint → test → claude-review`.

```bash
gh pr checks --watch
```

If `--watch` doesn't terminate normally, poll every ~30 seconds:
```bash
gh pr checks
```

### Step 6a — Lint failure

When the `lint` job fails:

1. Fetch the error details:
   ```bash
   gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId' | xargs gh run view --log-failed
   ```

2. Auto-fix locally:
   ```bash
   ruff check --fix
   ruff format
   ```

3. Commit the fixes and push, then go back to step 6:
   ```bash
   git add <fixed files>
   git commit -m "Fix lint errors"
   git push
   ```

### Step 6b — Test failure

When the `test` job fails:

1. Fetch the logs:
   ```bash
   gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId' | xargs gh run view --log-failed
   ```

2. Reproduce the failure locally:
   ```bash
   coverage run -m unittest discover
   coverage report -m
   ```

3. Identify and fix the root causes. Commit the fixes and push, then go back to step 6.

## Step 7 — Fetch and summarize Claude's code review

Once `claude-review` succeeds, fetch the comments:

```bash
# General PR comments (this is where Claude posts the Summary)
gh pr view --json comments --jq '.comments[] | "=== [\(.author.login)] ===\n\(.body)\n"'

# Inline comments on code lines
PR_NUM=$(gh pr view --json number --jq .number)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api "repos/$REPO/pulls/$PR_NUM/comments" --jq '.[] | "[\(.path):\(.line // .original_line)] \(.body)"'
```

Based on the gathered data, produce a concise summary:

```
## Code review result

**Status:** Approved / Changes requested

**What's OK:**
- <list of accepted items or "No comments on the current changes">

**Issues to consider:**
1. [file:line] (bug|security|performance) — description — suggested fix
2. ...

**Maintenance notes (optional):**
- ...
```

Then **ask the user** which issues to fix. Wait for a response before continuing.

## Step 8 — Apply approved fixes

Based on the user's decision, fix **only** what was approved. Commit and push:

```bash
git add <changed files>
git commit -m "Address code review: <what was fixed>"
git push
```

Go back to **step 6** — monitor the new pipeline run.

## Step 9 — Completion

Once the pipeline passes entirely and the review is positive (or "No issues found"):

Inform the user: the PR is merge-ready. Provide the PR link:
```bash
gh pr view --json url --jq .url
```

**Do not merge on your own.** Wait for the user's decision.
