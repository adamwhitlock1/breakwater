# Local stand-in for the Breakwater Sandbox image: Python 3.12 + valgrind (cachegrind) + uv + git.
# The same recipe becomes the ConTree image once Sandboxes access is granted.
#   docker build -f docker/harness.Dockerfile -t breakwater-harness .
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends valgrind git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

ENV PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/cache/uv
WORKDIR /work
