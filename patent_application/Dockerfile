# Patent Classifier – hardened container image
#
# Security measures applied (RISK-INFRA-2, RISK-APP-3):
#   - Non-root user: application runs as "appuser" (uid 1001)
#   - libmagic installed for server-side PDF MIME validation
#   - Only runtime files are copied (no source-control metadata, test files, etc.)
#   - pip cache disabled to reduce image size and avoid stale cache artefacts

FROM python:3.12-slim

# Install libmagic for python-magic PDF validation (RISK-APP-3)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install dependencies before application code so that the
# dependency layer is cached independently of code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root system user and group (RISK-INFRA-2).
# Running as root inside a container is unnecessary and broadens the blast
# radius of any container-escape vulnerability.
RUN groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup --no-create-home appuser

# Copy only the files the application needs at runtime
COPY doc.py prompt_config.txt ./
COPY .streamlit/ ./.streamlit/

# Transfer ownership to the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8081

# Streamlit flags:
#   --server.headless=true   suppresses browser-open prompt
#   --server.address=0.0.0.0 binds to all interfaces inside the container
CMD ["streamlit", "run", "doc.py", \
     "--server.port=8081", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
