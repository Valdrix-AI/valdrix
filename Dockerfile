# ============================================================
# STAGE 1: Build dependencies
# ============================================================
# python:3.12-slim as of 2026-02-28
FROM python:3.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS builder

# Labels for OCI compliance
LABEL org.opencontainers.image.source="https://github.com/valdrics/valdrics"
LABEL org.opencontainers.image.description="Valdrics AI - Autonomous FinOps & GreenOps Guardian"
LABEL org.opencontainers.image.licenses="BUSL-1.1"

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
FROM python:3.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS runtime

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=5)"

EXPOSE 8000

CMD ["/bin/sh", "-c", "python -c \"from app.shared.core.config import get_settings; from app.shared.core.runtime_dependencies import validate_runtime_dependencies; s=get_settings(); validate_runtime_dependencies(s); print('runtime_env_validation_passed', f'environment={s.ENVIRONMENT}')\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
