# Build the dashboard and ship it with the API.
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Prisma CLI is isolated from the Python runtime image.
FROM node:22-slim AS database
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1001 sre && useradd -u 1001 -g sre -s /usr/sbin/nologin -m sre
COPY package.json package-lock.json ./
RUN npm ci
COPY prisma.config.ts ./
COPY prisma/ ./prisma/
RUN chown -R sre:sre /app
USER sre
CMD ["npm", "run", "db:migrate"]

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN groupadd -g 1001 sre && useradd -u 1001 -g sre -s /usr/sbin/nologin -m sre
COPY --from=builder /install /usr/local
COPY --chown=sre:sre src/ ./src/
COPY --from=frontend --chown=sre:sre /frontend/dist ./frontend/dist
RUN mkdir -p /app/data && chown sre:sre /app/data
USER sre
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz')"
# The simulator is intentionally single-process: do not add multiple workers.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
