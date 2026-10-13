# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

# ---- base: dependencies only (cached until requirements.txt changes) ----
FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- test: used by GitHub Actions and Jenkins ----
FROM base AS test
COPY . .
CMD ["python", "-m", "pytest", "-q"]

# ---- runtime: non-root production image (default target) ----
FROM base AS runtime
RUN useradd --system --uid 10001 --no-create-home appuser
COPY --chown=appuser *.py ./
USER appuser
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/health', timeout=3)"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "app_v1_1:create_app()"]