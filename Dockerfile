ARG PYTHON_IMAGE=python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" MINING_DATA_DIR=/app/data MINING_MODE=demo MINING_AS_OF=2021-09-08
COPY data/manifest.json ./data/manifest.json
COPY data/replay.json ./data/replay.json
RUN useradd --create-home --uid 10001 brief && mkdir /app/outputs && \
    chmod -R a+rX /app/data && chown brief:brief /app/outputs
USER brief
ENTRYPOINT ["mining-brief"]
