FROM python:3.14.4-bookworm

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first so Docker can cache this layer
COPY pyproject.toml ./
RUN uv sync --no-dev

# Copy the actual application code
COPY src ./src

EXPOSE 8000

ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["--app-dir", "src", "--host", "0.0.0.0", "app:app"]