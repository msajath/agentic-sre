# ==============================================================================
# Production Dockerfile for Agentic SRE Platform
# Multi-stage, minimal attack surface, non-root security container
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Security: Create non-root user and group
RUN groupadd -g 1001 sre && \
    useradd -u 1001 -g sre -s /bin/bash -m sre

# Copy installed packages from builder
COPY --from=builder /root/.local /home/sre/.local
ENV PATH=/home/sre/.local/bin:$PATH

# Copy application source code
COPY --chown=sre:sre src/ ./src/
COPY --chown=sre:sre requirements.txt .

# Create data directory for SQLite database with correct permissions
RUN mkdir -p /app/data && chown -R sre:sre /app/data

# Switch to non-root user
USER sre

EXPOSE 8000

# Healthcheck probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# Start production server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
