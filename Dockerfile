# DAQS v5.1 Enterprise — single-container image
# Runs FastAPI (uvicorn :8001) + Streamlit (:8501) via supervisor

FROM python:3.12-slim

# ── System deps ──────────────────────────────────────────────────────────────
# libstdc++6  : fast-downward pre-built binary
# supervisor  : process manager for FastAPI + Streamlit in one container
RUN apt-get update && apt-get install -y --no-install-recommends \
        libstdc++6 \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ──────────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt

# ── Application code ─────────────────────────────────────────────────────────
COPY . .

# Pre-create writable runtime dirs (volume mounts may override them)
RUN mkdir -p logs static/images/locations static/images/personas generated/pddl_tests

# ── Supervisor config ─────────────────────────────────────────────────────────
COPY docker/supervisord.conf /etc/supervisor/conf.d/daqs.conf

# ── Ports ─────────────────────────────────────────────────────────────────────
EXPOSE 8001 8501

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/daqs.conf"]
