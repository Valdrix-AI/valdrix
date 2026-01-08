# ============================================================
# STAGE 1: Build dependencies
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files first (Docker cache optimization)
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache .

# ============================================================
# STAGE 2: Runtime (minimal image)
# ============================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Security: Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app ./app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]