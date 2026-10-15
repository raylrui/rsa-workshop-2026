import logging
import os
import struct

import boto3
import streamlit as st

# ── Logging ──────────────────────────────────────────────────────────────────
# All diagnostic output goes to the server log, never to the browser
# (RISK-APP-1: raw exceptions must not be surfaced to users).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Patent Classifier",
    page_icon="📄",
    layout="centered",
)

# ── Constants ─────────────────────────────────────────────────────────────────
# Cross-region inference profile for Claude Haiku 4.5 in us-east-1
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# System prompt loaded from SSM Parameter Store (RISK-APP-4).
# The parameter name is injected by the ECS task definition.
SSM_PROMPT_PARAM = os.environ.get(
    "SSM_PROMPT_PARAM", "/patent-classifier/system-prompt"
)

# Bedrock Guardrail IDs injected by the ECS task definition (RISK-APP-5).
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")

# File upload limits (RISK-APP-2)
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB hard limit

# Minimal PDF magic bytes: every PDF starts with "%PDF" (RISK-APP-3)
_PDF_MAGIC = b"%PDF"


# ── PDF validation ────────────────────────────────────────────────────────────
def _validate_pdf_magic(data: bytes) -> bool:
    """Return True if the first bytes match the PDF magic number (%PDF)."""
    return data[:4] == _PDF_MAGIC


# ── AWS clients ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_ssm_client():
    return boto3.client("ssm", region_name=REGION)


@st.cache_resource(show_spinner=False)
def _get_bedrock_client():
    """Return a boto3 Bedrock Runtime client.

    Inside AWS (ECS / EC2) the task/instance role is used automatically.
    Traffic is routed through the Bedrock VPC endpoint when one is
    present (RISK-NET-2); no code change is required — boto3 resolves
    the private DNS name transparently.
    """
    return boto3.client("bedrock-runtime", region_name=REGION)


# ── System prompt ─────────────────────────────────────────────────────────────
def load_system_prompt() -> str:
    """Load the system prompt from SSM Parameter Store (RISK-APP-4).

    Falls back to the bundled prompt_config.txt so the app still works
    in local development without AWS credentials.
    Changes to the SSM parameter take effect on the next page load
    (cache_data removed — RISK-APP-5 / correctness note in SECURITY_RISKS.md).
    """
    try:
        client = _get_ssm_client()
        resp = client.get_parameter(Name=SSM_PROMPT_PARAM, WithDecryption=True)
        return resp["Parameter"]["Value"].strip()
    except Exception:
        logger.warning(
            "Could not read system prompt from SSM (%s); "
            "falling back to prompt_config.txt",
            SSM_PROMPT_PARAM,
        )
        from pathlib import Path
        fallback = Path(__file__).parent / "prompt_config.txt"
        return fallback.read_text(encoding="utf-8").strip()


# ── Bedrock inference ─────────────────────────────────────────────────────────
def classify_patent(pdf_bytes: bytes, system_prompt: str) -> str:
    """Send the PDF to Claude via Bedrock and return the classification.

    Attaches the Bedrock Guardrail when GUARDRAIL_ID is configured so that
    prompt-injection attempts embedded in the uploaded PDF are intercepted
    before reaching the model (RISK-APP-5).
    """
    import base64
    import json

    client = _get_bedrock_client()

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Please classify this patent application according "
                            "to the IPC and explain your reasoning."
                        ),
                    },
                ],
            }
        ],
        "max_tokens": 2048,
    }

    invoke_kwargs: dict = dict(
        modelId=MODEL_ID,
        body=json.dumps(request_body),
        contentType="application/json",
        accept="application/json",
    )

    # Attach the guardrail when available (RISK-APP-5)
    if GUARDRAIL_ID:
        invoke_kwargs["guardrailIdentifier"] = GUARDRAIL_ID
        invoke_kwargs["guardrailVersion"] = GUARDRAIL_VERSION

    response = client.invoke_model(**invoke_kwargs)
    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📄 Patent Classifier")
st.markdown(
    "Upload a patent application PDF and click **Classify** to get an "
    "IPC classification powered by Amazon Bedrock."
)

uploaded_file = st.file_uploader(
    "Upload patent application (PDF)",
    type=["pdf"],
    help=f"Select a PDF file. Maximum size: {MAX_PDF_BYTES // (1024 * 1024)} MB.",
)

if uploaded_file is not None:
    st.success(f"File uploaded: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

    if st.button("Classify", type="primary"):
        # ── Server-side file-size check (RISK-APP-2) ──────────────────────────
        pdf_bytes = uploaded_file.read()
        if len(pdf_bytes) > MAX_PDF_BYTES:
            st.error(
                f"File too large ({len(pdf_bytes) / (1024*1024):.1f} MB). "
                f"Maximum allowed size is {MAX_PDF_BYTES // (1024*1024)} MB."
            )
            st.stop()

        # ── Server-side MIME / magic-byte check (RISK-APP-3) ─────────────────
        if not _validate_pdf_magic(pdf_bytes):
            logger.warning(
                "Rejected upload '%s': failed PDF magic-byte check "
                "(first 4 bytes: %r)",
                uploaded_file.name,
                pdf_bytes[:4],
            )
            st.error(
                "The uploaded file does not appear to be a valid PDF. "
                "Please upload a PDF document."
            )
            st.stop()

        # ── Load system prompt from SSM (RISK-APP-4) ──────────────────────────
        system_prompt = load_system_prompt()

        with st.spinner("Analysing patent and determining IPC classification…"):
            try:
                result = classify_patent(pdf_bytes, system_prompt)
                st.subheader("Classification Result")
                st.markdown(result)
            except Exception:
                # Log the full exception server-side; show only a safe generic
                # message to the user so AWS internals are never exposed
                # (RISK-APP-1).
                logger.exception(
                    "Bedrock invocation failed for file '%s'", uploaded_file.name
                )
                st.error(
                    "Classification failed. Please try again or contact support "
                    "if the problem persists."
                )
