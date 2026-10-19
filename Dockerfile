# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie

# GeoDjango needs the GDAL, GEOS, and PROJ shared libraries; gdal-bin pulls them in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" app && useradd --uid "$UID" --gid "$GID" --create-home app

# The virtualenv lives outside /app so bind-mounting the source in development
# doesn't hide it. Media and the Tailwind binary are pre-created so named
# volumes mounted there start out owned by the app user.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DJANGO_MEDIA_ROOT=/app/media \
    TAILWIND_CLI_PATH=/opt/tailwind
RUN mkdir -p /opt/venv /opt/tailwind /app/media && chown -R app:app /opt/venv /opt/tailwind /app

USER app
WORKDIR /app

ARG UV_SYNC_ARGS="--no-dev"
COPY --chown=app:app pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=${UID},gid=${GID} \
    uv sync --locked --no-install-project $UV_SYNC_ARGS

COPY --chown=app:app . .

EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3"]
