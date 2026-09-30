#!/usr/bin/env bash
# Fetch upstream and report changes without merging or modifying tracked files.
set -euo pipefail

UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"

git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1 || {
  echo "Missing Git remote: $UPSTREAM_REMOTE" >&2
  exit 1
}

echo "Fetching $UPSTREAM_REMOTE/$UPSTREAM_BRANCH..."
git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"

upstream_ref="$UPSTREAM_REMOTE/$UPSTREAM_BRANCH"
echo "Current branch: $(git branch --show-current)"
echo "Upstream:       $upstream_ref"
echo

echo "Changed files since upstream:"
git diff --stat HEAD "$upstream_ref" -- || true
echo

if git merge-base --is-ancestor "$upstream_ref" HEAD; then
  echo "Local branch includes the current upstream commit."
elif git merge-base --is-ancestor HEAD "$upstream_ref"; then
  echo "Upstream is ahead by:"
  git log --oneline HEAD.."$upstream_ref"
else
  echo "Branches have diverged. Review before merging:"
  git log --oneline --left-right --decorate HEAD..."$upstream_ref"
fi

echo
echo "No merge, rebase, reset, or file overwrite was performed."
