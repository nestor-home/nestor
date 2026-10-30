# Nestor server image. Build: docker build -t nestor . — run with compose.yaml.

# The admin front, built into the Python package's static folder (see web/vite.config.ts).
FROM node:22-slim AS web
RUN corepack enable
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
# pnpm installs the agent skills some packages ship (pnpm-workspace.yaml) into this git-ignored folder.
RUN mkdir -p .claude/skills && pnpm install --frozen-lockfile
COPY web ./
RUN pnpm build

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --all-extras --no-install-project
COPY src ./src
COPY --from=web /src/nestor/admin/static/app ./src/nestor/admin/static/app
RUN uv sync --locked --no-dev --all-extras

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 nestor
COPY --from=build --chown=nestor:nestor /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER nestor
WORKDIR /data
VOLUME ["/data"]
EXPOSE 7860 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1
ENTRYPOINT ["nestor", "-c", "/data/nestor.yaml"]
CMD ["run"]
