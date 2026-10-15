#!/usr/bin/env bash
# deploy-phase1.sh
# Deploys Phase 1 of the Patent Classifier infrastructure:
# the IAM roles required by the ECS tasks.
#
# Usage:
#   ./deploy-phase1.sh [--region <region>]
#
# Defaults:
#   region  = us-east-1
#
# Prerequisites:
#   - AWS CLI v2 installed and on PATH
#   - Caller identity must have iam:CreateRole, iam:AttachRolePolicy,
#     iam:PutRolePolicy, and cloudformation:* permissions.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
STACK_NAME="patent-classifier-iam"
REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/cfn/iam.yaml"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)
      REGION="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--region <region>]" >&2
      exit 1
      ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v aws &>/dev/null || fail "AWS CLI not found. Please install it first."

[[ -f "$TEMPLATE_FILE" ]] || fail "Template not found: $TEMPLATE_FILE"

CALLER_IDENTITY=$(aws sts get-caller-identity --region "$REGION" --output json 2>&1) \
  || fail "Unable to call STS. Check your credentials/network.\n$CALLER_IDENTITY"

ACCOUNT_ID=$(echo "$CALLER_IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
CALLER_ARN=$(echo "$CALLER_IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Arn'])")

log "Account : $ACCOUNT_ID"
log "Caller  : $CALLER_ARN"
log "Region  : $REGION"
log "Stack   : $STACK_NAME"
log "Template: $TEMPLATE_FILE"
echo

# ── Validate template ─────────────────────────────────────────────────────────
log "Validating CloudFormation template..."
aws cloudformation validate-template \
  --template-body "file://${TEMPLATE_FILE}" \
  --region "$REGION" \
  --output table
echo

# ── Deploy stack ──────────────────────────────────────────────────────────────
log "Deploying stack '$STACK_NAME'..."
aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$TEMPLATE_FILE" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --no-fail-on-empty-changeset

# ── Show outputs ──────────────────────────────────────────────────────────────
log "Stack deployed successfully. Outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs" \
  --output table

# ── Verify roles exist ────────────────────────────────────────────────────────
echo
log "Verifying IAM roles..."

for ROLE in patent-classifier-execution-role patent-classifier-task-role; do
  ROLE_ARN=$(aws iam get-role --role-name "$ROLE" \
    --query 'Role.Arn' --output text 2>&1) \
    || fail "Role '$ROLE' not found after deployment."
  log "  ✓ $ROLE_ARN"
done

echo
log "Phase 1 complete. IAM roles are ready."
log "You can now proceed to Phase 2 (container image build and ECR push)."
