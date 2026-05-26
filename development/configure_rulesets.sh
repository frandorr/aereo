#!/usr/bin/env bash
set -euo pipefail

# Ensure we are inside a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: This script must be run inside a git repository."
  exit 1
fi

# Fetch repository details from gh
REPO_INFO=$(gh repo view --json owner,name,isPrivate)
OWNER=$(echo "$REPO_INFO" | grep -oP '"owner":\s*\{\s*"id":[^,]+,\s*"login":\s*"\K[^"]+')
REPO_NAME=$(echo "$REPO_INFO" | grep -oP '"name":\s*"\K[^"]+')
IS_PRIVATE=$(echo "$REPO_INFO" | grep -oP '"isPrivate":\s*\K[a-z]+')

echo "Repository: $OWNER/$REPO_NAME"
echo "Private: $IS_PRIVATE"

if [ "$IS_PRIVATE" = "true" ]; then
  echo "⚠️  WARNING: Repository is private. Standard branch protection and rulesets require GitHub Pro or a paid team plan."
  echo "If you attempt to apply rulesets on a free private repository, the command will fail with a HTTP 403 error."
  echo "You can bypass this limitation by upgrading to GitHub Pro or changing repository visibility to public via:"
  echo "  gh repo edit --visibility public"
  echo ""
  read -p "Would you like to try applying the rulesets anyway? (y/N) " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
  fi
fi

echo "Applying main branch protection ruleset..."
gh api --method POST "/repos/$OWNER/$REPO_NAME/rulesets" \
  -H "Accept: application/vnd.github+json" \
  --input .github/rulesets/main-branch.json

echo "Applying release tags protection ruleset..."
gh api --method POST "/repos/$OWNER/$REPO_NAME/rulesets" \
  -H "Accept: application/vnd.github+json" \
  --input .github/rulesets/release-tags.json

echo "🎉 Done! Rulesets applied successfully."
