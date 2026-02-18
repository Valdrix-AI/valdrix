# ============================================================
# STAGE 1: Build dependencies
# ============================================================
# python:3.12-slim as of 2026-02-17
FROM python:3.12-slim@sha256:7f08d0e501538350cc6f4cf9b07decfa810ee9a4e0be8451104975f284c71887 AS builder

# Labels for OCI compliance
LABEL org.opencontainers.image.source="https://github.com/valdrix/valdrix"
LABEL org.opencontainers.image.description="Valdrix AI - Autonomous FinOps & GreenOps Guardian"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
ENV UV_SYSTEM_PYTHON=1
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into a dedicated path
RUN uv pip install --no-cache -r pyproject.toml

# ============================================================
# STAGE 2: Runtime (minimal image)
# ============================================================
FROM python:3.12-slim@sha256:7f08d0e501538350cc6f4cf9b07decfa810ee9a4e0be8451104975f284c71887 AS runtime

WORKDIR /app

# Security: Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser app ./app

# Metadata and Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]