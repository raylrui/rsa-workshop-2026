# Security Risk Assessment — Patent Classifier Application

**Date:** 2026-10-14  
**Scope:** `doc.py` (Streamlit application), `cfn/iam.yaml` (IAM CloudFormation stack),
`cfn/app.yaml` (ECS/ALB CloudFormation stack), `prompt_config.txt`, `requirements.txt`,
and the planned AWS deployment architecture described in `PLAN.md`.

**Risk rating scale:** 🔴 High · 🟡 Medium · 🟢 Low / Informational

---

## 1. Executive Summary

The application is a straightforward, single-purpose tool: users upload a PDF patent
application, which is forwarded to Amazon Bedrock (Claude Haiku 4.5 via a geographic
cross-region inference profile) for IPC classification. The attack surface is modest
for an internal tooling context, but several issues require attention before the
application handles confidential or regulated documents.

The most significant concerns are:

- The ALB serves plain HTTP — all document content is transmitted unencrypted.
- The application is publicly reachable on the internet with no authentication layer.
- Raw exception messages (including potential AWS error details) are surfaced directly
  to the browser.
- File upload has no server-side size or MIME-type enforcement.
- No audit logging of document submissions exists.

If there is **any possibility** that patent applications submitted through this tool
contain Protected Health Information (PHI) — for example, medical-device patents that
include patient data in their supporting materials — the HIPAA considerations in
section 5 apply directly. Even absent PHI, many of the hardening recommendations
below are appropriate for a tool that processes commercially sensitive, pre-grant
patent applications.

---

## 2. Network & Transport Security

### 🔴 RISK-NET-1 — Plain HTTP between users and the ALB

The `cfn/app.yaml` ALB listener uses `Protocol: HTTP` on port 80. Every PDF document,
system prompt, and classification result is transmitted in cleartext between the user's
browser and the load balancer. A network observer on the same path can read or modify
all content.

**Recommendation:** Add an HTTPS listener (port 443) backed by an ACM certificate.
Redirect HTTP → HTTPS with a 301 rule on the port-80 listener. Remove the plain
HTTP listener once HTTPS is confirmed working.

```yaml
# cfn/app.yaml additions
HttpsListener:
  Type: AWS::ElasticLoadBalancingV2::Listener
  Properties:
    LoadBalancerArn: !Ref Alb
    Protocol: HTTPS
    Port: 443
    Certificates:
      - CertificateArn: !Ref AcmCertArn   # parameter
    DefaultActions:
      - Type: forward
        TargetGroupArn: !Ref TargetGroup

HttpRedirectListener:
  Type: AWS::ElasticLoadBalancingV2::Listener
  Properties:
    LoadBalancerArn: !Ref Alb
    Protocol: HTTP
    Port: 80
    DefaultActions:
      - Type: redirect
        RedirectConfig:
          Protocol: HTTPS
          Port: "443"
          StatusCode: HTTP_301
```

### 🟡 RISK-NET-2 — Bedrock traffic traverses the public internet

ECS tasks are deployed with `AssignPublicIp: ENABLED` in public subnets. Bedrock
API calls egress through the internet gateway. Although TLS 1.2+ is always enforced
by Bedrock, traffic leaves the AWS network boundary.

**Recommendation:** Move ECS tasks to private subnets and add a VPC Interface
Endpoint for `com.amazonaws.us-east-1.bedrock-runtime`. This keeps Bedrock traffic
entirely within the AWS backbone and eliminates the public IP requirement for tasks.

```yaml
# cfn/app.yaml addition
BedrockRuntimeEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Properties:
    VpcEndpointType: Interface
    ServiceName: com.amazonaws.us-east-1.bedrock-runtime
    VpcId: !Ref VpcId
    SubnetIds: !Ref PrivateSubnets
    SecurityGroupIds:
      - !Ref EcsSecurityGroup
    PrivateDnsEnabled: true
```

### 🟡 RISK-NET-3 — ALB security group allows all inbound IPv4 and IPv6 traffic

`AlbSecurityGroup` currently permits `0.0.0.0/0`. If the application is intended
for a known set of users (e.g., internal staff on a corporate network or VPN),
restricting inbound access to known CIDRs significantly reduces the exposed
attack surface.

**Recommendation:** Parameterise the allowed CIDR and default it to the corporate
egress IP range. At minimum, add an IPv6 deny or restrict `CidrIpv6: ::/0`.

---

## 3. Authentication & Access Control

### 🔴 RISK-AUTH-1 — No user authentication on the application

The ALB has no authentication rule. Any person who can reach the endpoint can
immediately upload documents and invoke Bedrock, incurring costs and potentially
submitting sensitive IP to an LLM without authorisation.

**Recommendation:** Enable ALB-native OIDC authentication (e.g., via Cognito or
a corporate IdP). This requires no application code changes.

```yaml
# cfn/app.yaml — replace Listener DefaultActions with an authenticate-oidc action
DefaultActions:
  - Type: authenticate-oidc
    Order: 1
    AuthenticateOidcConfig:
      Issuer: https://cognito-idp.us-east-1.amazonaws.com/<user-pool-id>
      AuthorizationEndpoint: ...
      TokenEndpoint: ...
      UserInfoEndpoint: ...
      ClientId: !Ref OidcClientId
      ClientSecret: !Ref OidcClientSecret
      OnUnauthenticatedRequest: authenticate
  - Type: forward
    Order: 2
    TargetGroupArn: !Ref TargetGroup
```

### 🟡 RISK-AUTH-2 — IAM Task Role has no resource tag condition

The Bedrock inference permissions are scoped by resource ARN (correct), but there
is no additional `aws:RequestedRegion` condition on the inference profile statement.
If the account ever gains additional inference profiles, the policy remains
correctly scoped because the ARN is explicit. No change required for correctness,
but adding a `aws:RequestedRegion: us-east-1` condition to the first statement
further limits blast radius.

---

## 4. Application-Level Security

### 🔴 RISK-APP-1 — Raw exception messages exposed to users

In `doc.py`, exceptions from Bedrock are rendered directly into the UI:

```python
st.error(f"An error occurred while calling Bedrock: {exc}")
```

AWS SDK exceptions can contain account IDs, role ARNs, request IDs, and service
internals. This information is useful to an attacker mapping the account's
configuration.

**Recommendation:** Log the full exception server-side and show only a generic
message to users:

```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).exception("Bedrock call failed")
    st.error("Classification failed. Please try again or contact support.")
```

### 🟡 RISK-APP-2 — No server-side file size limit

`st.file_uploader` accepts any size by default. A user (or attacker) can upload
an extremely large PDF, exhausting Bedrock's context window, causing high token
costs, or triggering timeouts/OOM conditions in the container.

**Recommendation:** Enforce a maximum file size in application code before the
Bedrock call:

```python
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

pdf_bytes = uploaded_file.read()
if len(pdf_bytes) > MAX_PDF_BYTES:
    st.error(f"File too large. Maximum allowed size is 20 MB.")
    st.stop()
```

You can also set `server.maxUploadSize` in Streamlit config (`.streamlit/config.toml`).

### 🟡 RISK-APP-3 — MIME type validated only by Streamlit's client-side filter

`st.file_uploader(type=["pdf"])` filters file extensions in the browser, but the
server receives whatever bytes the client sends. A malicious actor can rename
any file `.pdf` and submit it.

**Recommendation:** Validate the magic bytes server-side before the Bedrock call:

```python
import magic  # python-magic (requires libmagic)

mime = magic.from_buffer(pdf_bytes[:2048], mime=True)
if mime != "application/pdf":
    st.error("Uploaded file does not appear to be a valid PDF.")
    st.stop()
```

Add `python-magic` to `requirements.txt`.

### 🟡 RISK-APP-4 — System prompt loaded from a world-readable flat file

`prompt_config.txt` is co-located with application code and world-readable inside
the container. If an operator modifies this file to inject adversarial instructions,
the application will silently change its behaviour with no audit trail.

**Recommendation:** Store the system prompt in AWS Systems Manager Parameter Store
(or Secrets Manager for higher sensitivity). Load it at container start with
appropriate IAM permissions, and add a `ssm:GetParameter` statement to the Task Role.
Changes to the parameter are automatically logged in CloudTrail.

### 🟢 RISK-APP-5 — `st.cache_data` on the system prompt suppresses hot-reload

`load_system_prompt()` is decorated with `@st.cache_data`, which persists across
sessions for the lifetime of the Streamlit process. If an operator updates
`prompt_config.txt`, the running container does not pick up the change without
a restart. This is a correctness/operations issue rather than a security risk,
but it interacts with RISK-APP-4: an attacker who modifies the prompt file must
also trigger a restart to activate the change.

### 🟡 RISK-APP-5 — No Bedrock Guardrails configured

The application sends raw user-uploaded PDF content directly to the model with no
content filtering. A specially crafted document could attempt prompt injection —
embedding hidden instructions in the PDF text to override the system prompt,
extract the system prompt, or make the model behave inappropriately.

**Recommendation:** Create a Bedrock Guardrail with at minimum:
- `PROMPT_ATTACK` content filter set to HIGH.
- A denied-topics policy blocking requests to disclose the system prompt or
  perform tasks unrelated to patent classification.

Reference the guardrail ID in the `invoke_model` call:

```python
response = client.invoke_model(
    modelId=MODEL_ID,
    body=json.dumps(request_body),
    contentType="application/json",
    accept="application/json",
    guardrailIdentifier="<guardrail-id>",
    guardrailVersion="DRAFT",
)
```

---

## 5. HIPAA Considerations

Amazon Bedrock is **HIPAA-eligible** (confirmed by AWS documentation across
FedRAMP Moderate, SOC 1/2/3, ISO 27001, and HIPAA BAA scope). However,
eligibility alone does not create compliance — the following conditions must
also be met:

### 🔴 RISK-HIPAA-1 — BAA required before processing any PHI

AWS requires a signed Business Associate Agreement (BAA) before any PHI may be
processed through a HIPAA-eligible service. Without a BAA, processing PHI through
Bedrock is a HIPAA violation regardless of how well the infrastructure is secured.

**Action required:** If patent documents submitted through this tool may contain
PHI (e.g., medical-device patents with patient data in supporting materials),
confirm that a BAA with AWS is in place and that Bedrock is listed within its scope.

### 🔴 RISK-HIPAA-2 — Cross-region inference and data residency

This application uses the `us.anthropic.claude-haiku-4-5-20251001-v1:0`
**geographic** (US-only) cross-region inference profile. Per AWS documentation:

> *"Your input prompts and output results might move outside of your source Region
> during cross-region inference. To the extent we store data for abuse detection,
> your input prompts and output results will be stored in the destination region."*

The destination regions for this profile are `us-east-1`, `us-east-2`, and
`us-west-2`. Abuse-detection data may be stored in any of these regions.

For a HIPAA use case this means:
- The BAA must cover all three destination regions.
- The PHI residency documentation must acknowledge multi-region storage.
- The geographic profile keeps data within the US, which is acceptable under
  most US-based HIPAA programs, but must be explicitly confirmed with legal counsel.

**Recommendation:** If HIPAA compliance is required, consider switching to a
**single-region** endpoint using the `bedrock-mantle` endpoint with the bare
model ID `anthropic.claude-haiku-4-5` to eliminate cross-region data movement.
This trades off throughput/availability for strict data residency.

### 🟡 RISK-HIPAA-3 — Audit logging not enabled

HIPAA requires an audit trail of all access to PHI, including which user submitted
which document and when. Currently:
- There is no user authentication (RISK-AUTH-1), so individual access cannot be
  attributed.
- Bedrock model invocation logging is not enabled.
- CloudTrail is assumed to be account-level but is not explicitly configured in
  the IaC.

**Recommendation:**
1. Enable Bedrock model invocation logging to CloudWatch Logs or S3 with a
   minimum 6-year retention policy (HIPAA requirement).
2. Enable CloudTrail in all regions, with log file integrity validation.
3. Implement user authentication (RISK-AUTH-1) so that each invocation is
   attributable to an identity.

### 🟡 RISK-HIPAA-4 — No encryption at rest for uploaded documents

Uploaded PDFs exist only in container memory during the Streamlit session —
they are not persisted to disk. This is good. However, if a future change adds
temporary file storage, S3 staging, or caching, those stores must use
customer-managed KMS keys to meet HIPAA's encryption-at-rest requirement and
the AWS Security Hub `Bedrock.1` control.

### 🟡 RISK-HIPAA-5 — CloudWatch log group lacks encryption

The `cfn/app.yaml` CloudWatch log group (`/ecs/patent-classifier`) does not
specify a KMS key. If container logs ever include fragments of document content
or stack traces containing data, those logs are encrypted with AWS-managed keys
only.

**Recommendation:** Add a `KmsKeyId` to the log group resource:

```yaml
LogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: /ecs/patent-classifier
    RetentionInDays: 30
    KmsKeyId: !Sub arn:aws:kms:us-east-1:${AWS::AccountId}:key/<key-id>
```

---

## 6. Infrastructure / IaC Security

### 🟡 RISK-INFRA-1 — ECR image scanning enabled but no action on findings

`ScanOnPush: true` is set on the ECR repository (good). However, there is no
SNS notification, EventBridge rule, or CI gate that acts on scan findings.
A container with critical CVEs could be deployed silently.

**Recommendation:** Add an EventBridge rule that triggers an SNS alert (or
blocks deployment) when ECR reports `CRITICAL` or `HIGH` severity findings.

### 🟡 RISK-INFRA-2 — Container runs as root

The Dockerfile (in `PLAN.md`) does not add a non-root user. The Streamlit process
inside the container runs as root, which broadens the impact of any container
escape vulnerability.

**Recommendation:** Add a non-root user to the Dockerfile:

```dockerfile
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser
```

### 🟡 RISK-INFRA-3 — Unpinned dependency versions

`requirements.txt` lists `streamlit` and `boto3` without version pins. Unpinned
dependencies mean the image content changes on every build, making builds
non-reproducible and introducing the risk of pulling a compromised or
breaking release.

**Recommendation:** Pin exact versions:

```
streamlit==1.45.1
boto3==1.38.36
```

Use `pip-compile` (from `pip-tools`) to generate a locked `requirements.txt`
from a `requirements.in` source file.

### 🟡 RISK-INFRA-4 — ECS tasks use latest image tag

`cfn/app.yaml` uses `ImageTag: latest` as the default parameter. The `latest` tag
is mutable — a bad push silently replaces the running image on the next task
restart. There is no rollback target.

**Recommendation:** Use immutable, versioned image tags (e.g., the Git commit
SHA). Update the CloudFormation parameter on each release.

### 🟢 RISK-INFRA-5 — CloudWatch log retention set to 30 days

30 days may be insufficient for audit or forensics purposes. For regulated
workloads, 1 year is a common baseline; HIPAA requires 6 years.

**Recommendation:** Increase `RetentionInDays` to at least 365, or to 2192 (6 years)
for HIPAA-covered workloads.

### 🟢 RISK-INFRA-6 — No VPC Flow Logs

There are no VPC Flow Logs enabled in the IaC. Flow logs provide network-level
visibility for incident response and anomaly detection.

**Recommendation:** Enable VPC Flow Logs to CloudWatch Logs or S3 on the
default VPC.

---

## 7. Summary Table

| ID | Severity | Category | Finding | Remediated? |
|----|----------|----------|---------|-------------|
| RISK-NET-1 | 🔴 High | Network | Plain HTTP — no TLS between user and ALB | No |
| RISK-NET-2 | 🟡 Medium | Network | Bedrock traffic via public internet | No |
| RISK-NET-3 | 🟡 Medium | Network | ALB open to all inbound IPs | No |
| RISK-AUTH-1 | 🔴 High | Auth | No user authentication | No |
| RISK-AUTH-2 | 🟡 Medium | Auth | No region condition on IAM inference profile statement | No |
| RISK-APP-1 | 🔴 High | Application | Raw AWS exceptions exposed to browser | No |
| RISK-APP-2 | 🟡 Medium | Application | No server-side file size limit | No |
| RISK-APP-3 | 🟡 Medium | Application | MIME type not validated server-side | No |
| RISK-APP-4 | 🟡 Medium | Application | System prompt in unversioned flat file | No |
| RISK-APP-5 | 🟡 Medium | Application | No Bedrock Guardrails (prompt injection risk) | No |
| RISK-HIPAA-1 | 🔴 High | HIPAA | BAA required before processing any PHI | Verify |
| RISK-HIPAA-2 | 🔴 High | HIPAA | Cross-region data movement for abuse detection | Verify |
| RISK-HIPAA-3 | 🟡 Medium | HIPAA | No audit logging or identity attribution | No |
| RISK-HIPAA-4 | 🟡 Medium | HIPAA | No plan for encryption-at-rest if storage added | No |
| RISK-HIPAA-5 | 🟡 Medium | HIPAA | CloudWatch log group lacks customer KMS key | No |
| RISK-INFRA-1 | 🟡 Medium | Infra | ECR scan findings produce no alerts | No |
| RISK-INFRA-2 | 🟡 Medium | Infra | Container runs as root | No |
| RISK-INFRA-3 | 🟡 Medium | Infra | Unpinned dependency versions | No |
| RISK-INFRA-4 | 🟡 Medium | Infra | Mutable `latest` image tag | No |
| RISK-INFRA-5 | 🟢 Low | Infra | CloudWatch log retention too short for regulated use | No |
| RISK-INFRA-6 | 🟢 Low | Infra | No VPC Flow Logs | No |

---

## 8. Recommended Remediation Priority

**Immediate (before first production use):**
1. RISK-NET-1 — Enable HTTPS on the ALB.
2. RISK-AUTH-1 — Add authentication (ALB OIDC / Cognito).
3. RISK-APP-1 — Sanitise exception messages shown to users.
4. RISK-HIPAA-1 — Confirm or obtain a BAA with AWS if PHI may be processed.

**Short-term (within first sprint after go-live):**
5. RISK-APP-5 — Enable Bedrock Guardrails with PROMPT_ATTACK filter.
6. RISK-APP-2 — Enforce file size limit in application code.
7. RISK-APP-3 — Validate PDF magic bytes server-side.
8. RISK-INFRA-2 — Run container as non-root.
9. RISK-INFRA-3 — Pin dependency versions.
10. RISK-NET-2 — Add Bedrock VPC endpoint and move tasks to private subnets.

**Medium-term (hardening backlog):**
11. RISK-HIPAA-2 — Evaluate single-region inference if strict data residency is required.
12. RISK-HIPAA-3 — Enable Bedrock invocation logging and CloudTrail.
13. RISK-APP-4 — Move system prompt to SSM Parameter Store.
14. RISK-INFRA-1 — Alert on ECR critical scan findings.
15. RISK-INFRA-4 — Switch to versioned image tags.
16. RISK-HIPAA-5 — Add customer KMS key to CloudWatch log group.
17. RISK-INFRA-5 — Increase log retention to ≥365 days.
18. RISK-INFRA-6 — Enable VPC Flow Logs.

---

## 9. AWS Documentation References

The following AWS documentation pages were consulted during this assessment:

| Topic | URL |
|-------|-----|
| Bedrock security and compliance overview | https://aws.amazon.com/bedrock/security-compliance/ |
| Bedrock HIPAA eligibility and compliance standards | https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture-generative-ai/gen-ai-sra.html |
| Geographic cross-region inference — data residency and IAM policy requirements | https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html |
| Claude Haiku 4.5 model card — inference profile IDs and destination regions | https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html |
| Bedrock Guardrails — prompt attack and content filtering | https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html |
| Security Hub CSPM controls for Bedrock (KMS encryption) | https://docs.aws.amazon.com/securityhub/latest/userguide/bedrock-controls.html |
| Bedrock abuse detection and data retention in cross-region inference | https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html |
