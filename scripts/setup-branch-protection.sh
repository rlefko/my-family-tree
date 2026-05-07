#!/usr/bin/env bash
# Apply recommended branch-protection rules to main. Requires a maintainer with
# admin scope. Idempotent. Update OWNER/REPO before running.
set -euo pipefail

OWNER="${1:-rlefkowitz}"
REPO="${2:-my-family-tree}"

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/$OWNER/$REPO/branches/main/protection" \
  -F required_status_checks.strict=true \
  -f "required_status_checks.contexts[]=backend (lint + typecheck)" \
  -f "required_status_checks.contexts[]=backend (unit tests)" \
  -f "required_status_checks.contexts[]=frontend (lint + test + build)" \
  -f "required_status_checks.contexts[]=terraform (fmt + validate)" \
  -f "required_status_checks.contexts[]=docker (smoke build)" \
  -F enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.dismiss_stale_reviews=true \
  -F required_pull_request_reviews.require_code_owner_reviews=true \
  -F required_linear_history=true \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -F required_conversation_resolution=true

echo "branch protection applied to $OWNER/$REPO main"
