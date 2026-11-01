FROM docker:27.5.1-cli AS docker-cli

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    TMPDIR=/var/lib/faultline/workspaces \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 faultline \
    && useradd --system --uid 10001 --gid faultline --create-home \
        --home-dir /home/faultline --shell /usr/sbin/nologin faultline \
    && install -d --owner=faultline --group=faultline /app /var/lib/faultline/workspaces

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY alembic.ini .
RUN python -m pip install --no-cache-dir .

RUN chown -R faultline:faultline /app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=20s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=15).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
