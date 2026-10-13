FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM deps AS runtime

RUN useradd --system --uid 10001 --no-create-home appuser

COPY --chown=appuser:appuser app/ ./app/

ENV PYTHONPATH=/app

USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "app.app_1_1:create_app()"]