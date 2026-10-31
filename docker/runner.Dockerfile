FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m pip install --no-cache-dir pytest==8.3.5 \
    && groupadd --gid 1000 runner \
    && useradd --uid 1000 --gid runner --no-create-home --shell /usr/sbin/nologin runner \
    && mkdir /workspace \
    && chown runner:runner /workspace

WORKDIR /workspace
USER 1000:1000

CMD ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
