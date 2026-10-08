FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends libportaudio2 ffmpeg build-essential git \
 && rm -rf /var/lib/apt/lists/*

# The repo is mounted read-only at /repo and is owned by another user
RUN git config --global --add safe.directory /repo

# Install only the dependencies, the code under test is copied in at run time.
# The CPU build of torch is a few GB smaller and the tests do not need a GPU.
WORKDIR /deps
COPY pyproject.toml .
RUN mkdir -p src/edceleste && touch src/edceleste/__init__.py \
 && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu ".[test,mutation]" \
 && pip uninstall -y edceleste

WORKDIR /work
