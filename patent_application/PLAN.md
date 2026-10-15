# Patent Classifier – AWS Deployment Plan (Hardened)

> This document reflects the **security-hardened** architecture produced after
> the security review in `SECURITY_RISKS.md`. Changes from the original plan
> are summarised in the [Change Log](#change-log) at the end.

## Overview

The application is a Streamlit web app that accepts PDF patent applications and
classifies them using Amazon Bedrock (Claude Haiku 4.5 via a US geographic
cross-region inference profile). The deployment targets **us-east-1** and is
fully managed through CloudFormation.

| Service | Purpose |
|---------|---------|
| Amazon ECR | Container image registry (immutable tags, scan-on-push) |
| Amazon ECS on Fargate | Serverless container runtime (private subnets) |
| Application Load Balancer | HTTPS endpoint with HTTP→HTTPS redirect |
| ACM | TLS certificate for the ALB HTTPS listener |
| Amazon Bedrock | LLM inference via `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Bedrock Guardrails | Prompt-injection protection and off-topic blocking |
| VPC Interface Endpoint | Private Bedrock connectivity (no internet egress) |
| AWS KMS | Customer-managed key for all CloudWatch log groups |
| AWS SSM Parameter Store | System prompt storage with audit trail |
| VPC Flow Logs | Network-level audit log |
| SNS | ECR vulnerability scan alerts |
| IAM | Least-privilege execution and task roles |
| CloudWatch Logs | Encrypted container, VPC flow, and Bedrock invocation logs |

All AWS resources are managed through **two CloudFormation stacks**:

| Stack | Template | Contents |
|-------|----------|---------|
| `patent-classifier-iam` | `cfn/iam.yaml` | IAM roles and least-privilege policies |
| `patent-classifier-app` | `cfn/app.yaml` | All other infrastructure |

---

## Prerequisites

Before deploying, complete the following out-of-band steps:

1. **ACM certificate** – Request or import a certificate for your domain in
   `us-east-1`. Note the ARN for the `AcmCertificateArn` parameter.

2. **Private subnets** – The ECS tasks must run in private subnets (no public
   IP). Create at least two private subnets with a NAT Gateway, or provide the
   IDs of existing ones. Update the `PrivateSubnets` parameter.

3. **SSM system prompt** – Store the system prompt before starting the service:

   ```bash
   aws ssm put-parameter \
     --name /patent-classifier/system-prompt \
     --type SecureString \
     --value "$(cat prompt_config.txt)" \
     --region us-east-1
   ```

4. **SNS subscription** – After the app stack is deployed, subscribe your
   security team's email to the `patent-classifier-security-alerts` topic so
   that ECR vulnerability scan findings generate notifications.

5. **BAA (if handling PHI)** – If patent documents may contain Protected Health
   Information, ensure an AWS Business Associate Agreement is in place and that
   Bedrock is in scope before deploying.

---

## Phase 1 – IAM Stack

> **Deploy this stack before anything else.** Only IAM roles and policies are
> created here — no compute resources.

### Template: `cfn/iam.yaml`

The Task Role policy now contains four statements:

| Sid | Purpose | Risk addressed |
|-----|---------|----------------|
| `AllowGeoCrisInferenceProfileAccess` | Invoke the `us.*` inference profile from `us-east-1` only | RISK-AUTH-2 |
| `AllowGeoCrisFoundationModelAccess` | Invoke the FM in all three US destination regions, scoped to the profile ARN | Bedrock IAM requirement |
| `AllowSsmReadSystemPrompt` | Read the system prompt from SSM Parameter Store | RISK-APP-4 |
| `AllowBedrockInvocationLogging` | Write to the Bedrock invocation log group | RISK-HIPAA-3 |

### Deploy Phase 1

```bash
aws cloudformation deploy \
  --stack-name patent-classifier-iam \
  --template-file cfn/iam.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Verify Phase 1

```bash
aws cloudformation describe-stacks \
  --stack-name patent-classifier-iam \
  --region us-east-1 \
  --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}'
```

Expected status: `CREATE_COMPLETE`

---

## Phase 2 – Container Image (ECR)

The ECR repository is created by the app stack. Deploy the app stack with
`DesiredCount=0` first to create the repository, then build and push the image.

### Dockerfile security changes

- `libmagic1` installed for server-side PDF MIME validation (`python-magic`)
- Non-root system user `appuser` (uid 1001) runs the Streamlit process
- Only runtime files are copied into the image

### Build and push

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
REPO=patent-classifier
VERSION=1.0.0          # use the same value as ImageTag parameter

aws ecr get-login-password --region $REGION \
  | docker login --username AWS \
                 --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

docker build -t $REPO:$VERSION .

docker tag $REPO:$VERSION \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:$VERSION

docker push \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:$VERSION
```

> **Note:** The ECR repository has `ImageTagMutability: IMMUTABLE`. The `:latest`
> tag is intentionally blocked. Use explicit version tags on every push.

---

## Phase 3 – Application Stack (ECS + ALB + supporting resources)

### Template: `cfn/app.yaml`

Key resources created in this stack:

| Resource | Notes |
|----------|-------|
| `LogsKmsKey` | Customer-managed KMS key; all log groups are encrypted with it |
| `AppLogGroup`, `FlowLogsLogGroup`, `BedrockInvocationLogGroup` | KMS-encrypted, configurable retention |
| `EcrRepo` | Immutable tags, scan-on-push |
| `EcrScanAlertRule` | EventBridge → SNS alert on CRITICAL ECR findings |
| `BedrockRuntimeEndpoint` | VPC Interface Endpoint; keeps Bedrock traffic off the internet |
| `AlbSecurityGroup` | Allows 80 (redirect only) and 443 |
| `EcsSecurityGroup` | Allows 8081 from ALB only |
| `VpcEndpointSecurityGroup` | Allows 443 from ECS tasks |
| `Alb` | Deletion protection enabled |
| `HttpListener` | Permanent 301 redirect → HTTPS |
| `HttpsListener` | TLS 1.3 preferred (`ELBSecurityPolicy-TLS13-1-2-2021-06`) |
| `PatentClassifierGuardrail` | PROMPT_ATTACK filter HIGH; denies system-prompt disclosure and off-topic requests |
| `VpcFlowLog` | ALL traffic on the VPC, delivered to CloudWatch |
| `Service` | `AssignPublicIp: DISABLED`; runs in private subnets |

### Deploy Phase 3

**Step 3a** – Deploy with zero tasks to create the ECR repository before the
image push:

```bash
aws cloudformation deploy \
  --stack-name patent-classifier-app \
  --template-file cfn/app.yaml \
  --parameter-overrides \
      DesiredCount=0 \
      AcmCertificateArn=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT-ID \
      PrivateSubnets=subnet-XXXXXXXX,subnet-YYYYYYYY \
      ImageTag=1.0.0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Step 3b** – Build and push the Docker image (see Phase 2 commands above).

**Step 3c** – Update the stack to start the service:

```bash
aws cloudformation deploy \
  --stack-name patent-classifier-app \
  --template-file cfn/app.yaml \
  --parameter-overrides \
      DesiredCount=1 \
      AcmCertificateArn=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT-ID \
      PrivateSubnets=subnet-XXXXXXXX,subnet-YYYYYYYY \
      ImageTag=1.0.0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

---

## Phase 4 – Post-deploy configuration

### Subscribe to security alerts

```bash
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name patent-classifier-app \
  --query 'Stacks[0].Outputs[?OutputKey==`SecurityAlertsTopicArn`].OutputValue' \
  --output text --region us-east-1)

aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint security-team@example.com \
  --region us-east-1
```

### Enable Bedrock invocation logging

Bedrock invocation logging is configured at the account level, not per-stack.
Run this once after the app stack is deployed:

```bash
LOG_GROUP_ARN=$(aws logs describe-log-groups \
  --log-group-name-prefix /aws/bedrock/patent-classifier \
  --query 'logGroups[0].arn' --output text --region us-east-1)

aws bedrock put-model-invocation-logging-configuration \
  --logging-config "{
    \"cloudWatchConfig\": {
      \"logGroupName\": \"/aws/bedrock/patent-classifier\",
      \"roleArn\": \"$(aws cloudformation describe-stacks \
        --stack-name patent-classifier-iam \
        --query 'Stacks[0].Outputs[?OutputKey==\`TaskRoleArn\`].OutputValue' \
        --output text --region us-east-1)\"
    },
    \"embeddingDataDeliveryEnabled\": false,
    \"imageDataDeliveryEnabled\": false,
    \"textDataDeliveryEnabled\": true
  }" \
  --region us-east-1
```

---

## Phase 5 – Verification & Smoke Test

```bash
# Confirm both stacks are healthy
aws cloudformation describe-stacks \
  --region us-east-1 \
  --query 'Stacks[?starts_with(StackName,`patent-classifier`)].{Name:StackName,Status:StackStatus}' \
  --output table

# Get the application URL
aws cloudformation describe-stacks \
  --stack-name patent-classifier-app \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`AppUrlHttps`].OutputValue' \
  --output text

# Confirm the ECS service has a running task
aws ecs describe-services \
  --cluster patent-classifier-cluster \
  --services patent-classifier-svc \
  --region us-east-1 \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

Tail container logs:

```bash
aws logs tail /ecs/patent-classifier --follow --region us-east-1
```

---

## Updating the application

```bash
VERSION=1.1.0   # increment for every release

# Build and push the new image
docker build -t patent-classifier:$VERSION .
docker tag patent-classifier:$VERSION \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/patent-classifier:$VERSION
docker push \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/patent-classifier:$VERSION

# Deploy – CloudFormation detects the ImageTag change and forces a new task
aws cloudformation deploy \
  --stack-name patent-classifier-app \
  --template-file cfn/app.yaml \
  --parameter-overrides ImageTag=$VERSION \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

---

## Rollback

```bash
# Roll back the app stack to its last stable state
aws cloudformation rollback-stack \
  --stack-name patent-classifier-app \
  --region us-east-1

# Full tear-down (app stack first, IAM stack second)
aws cloudformation delete-stack \
  --stack-name patent-classifier-app \
  --region us-east-1

aws cloudformation delete-stack \
  --stack-name patent-classifier-iam \
  --region us-east-1
```

> Delete the app stack **before** the IAM stack because the app stack imports
> outputs (role ARNs) from the IAM stack.

---

## Remaining hardening items (out of scope for this release)

| Item | Risk ID | Notes |
|------|---------|-------|
| ALB OIDC / Cognito authentication | RISK-AUTH-1 | Requires IdP configuration; high value for any non-internal deployment |
| Single-region inference (HIPAA strict residency) | RISK-HIPAA-2 | Switch to `bedrock-mantle` endpoint with bare model ID if PHI involved |
| Restrict ALB inbound CIDR | RISK-NET-3 | Add corporate egress IP as ALB security group parameter |
| Increase log retention to 2192 days | RISK-HIPAA-3 | Set `LogRetentionDays=2192` parameter for HIPAA workloads |

---

## Change Log

| Change | Files | Risk addressed |
|--------|-------|----------------|
| HTTPS listener + HTTP→HTTPS redirect | `cfn/app.yaml` | RISK-NET-1 |
| Bedrock VPC Interface Endpoint; `AssignPublicIp: DISABLED` | `cfn/app.yaml` | RISK-NET-2 |
| ALB security group scoped to 80+443 only | `cfn/app.yaml` | RISK-NET-3 |
| `aws:RequestedRegion: us-east-1` condition on inference profile statement | `cfn/iam.yaml` | RISK-AUTH-2 |
| Exception messages sanitised; full error logged server-side | `doc.py` | RISK-APP-1 |
| 20 MB file-size limit enforced in Python and Streamlit config | `doc.py`, `.streamlit/config.toml` | RISK-APP-2 |
| PDF magic-byte validation before Bedrock call; `python-magic` added | `doc.py`, `requirements.txt` | RISK-APP-3 |
| System prompt moved to SSM Parameter Store; `ssm:GetParameter` added to Task Role | `doc.py`, `cfn/iam.yaml` | RISK-APP-4 |
| Bedrock Guardrail with PROMPT_ATTACK HIGH filter and denied-topic policies | `cfn/app.yaml`, `doc.py` | RISK-APP-5 |
| Bedrock invocation log group and `logs:PutLogEvents` in Task Role | `cfn/app.yaml`, `cfn/iam.yaml` | RISK-HIPAA-3 |
| KMS customer-managed key on all three CloudWatch log groups | `cfn/app.yaml` | RISK-HIPAA-5 |
| EventBridge rule → SNS alert on CRITICAL ECR scan findings | `cfn/app.yaml` | RISK-INFRA-1 |
| Non-root `appuser` (uid 1001) in Dockerfile | `Dockerfile` | RISK-INFRA-2 |
| Exact version pins in `requirements.txt` | `requirements.txt` | RISK-INFRA-3 |
| `ImageTagMutability: IMMUTABLE` on ECR repo; `ImageTag` parameter default `1.0.0` | `cfn/app.yaml` | RISK-INFRA-4 |
| `LogRetentionDays` parameter (default 365) | `cfn/app.yaml` | RISK-INFRA-5 |
| VPC Flow Logs to KMS-encrypted CloudWatch log group | `cfn/app.yaml` | RISK-INFRA-6 |
