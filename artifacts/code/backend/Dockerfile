# ── Stage 1: Builder ──────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies:
# - tmux: for factory session management
# - procps: for ps/uptime commands used by psutil
# - curl: for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create non-root user (runs as root for tmux/docker socket access in v1.0)
# In production, configure with proper group permissions
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["python", "-m", "app.main"]
