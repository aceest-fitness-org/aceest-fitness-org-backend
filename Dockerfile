# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Lets the pipelines find and clean up only this project's images
LABEL project="aceest-api"

WORKDIR /app

# ---- Dependencies ----
FROM base AS deps

COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Tests ----
FROM deps AS test

COPY . .
CMD ["python", "-m", "pytest", "-q"]

# ---- Production runtime ----
FROM deps AS runtime

# Optional: pin a version at build time (--build-arg APP_MODULE=app_v1_2).
# Empty means "serve the newest app/app_v*.py", chosen by wsgi.py at start-up.
ARG APP_MODULE=""
ENV APP_MODULE=${APP_MODULE}

RUN useradd --system --uid 10001 --no-create-home appuser

COPY --chown=appuser:appuser wsgi.py ./
COPY --chown=appuser:appuser app ./app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/health', timeout=3)"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "wsgi:create_app()"]
