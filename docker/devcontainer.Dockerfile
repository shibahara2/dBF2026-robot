ARG CORE_IMAGE=robot-core:latest
FROM ${CORE_IMAGE}

COPY --from=node:22-bookworm-slim /usr/local/ /usr/local/

ENV CODEX_HOME=/opt/codex-home

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libstdc++6 \
    && npm install --global @openai/codex \
    && mkdir -p "$CODEX_HOME" /workspace \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
