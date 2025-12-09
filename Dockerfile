FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir \
    lancedb>=0.5.0 \
    ollama>=0.1.0 \
    mcp>=1.0.0 \
    watchdog>=4.0.0 \
    numpy>=1.24.0 \
    rich>=13.0.0 \
    typer>=0.9.0 \
    httpx>=0.25.0 \
    pyyaml>=6.0.0

# Copy source code
COPY src /app/src
COPY pyproject.toml /app/
COPY config.yaml /app/

# Create data directory
RUN mkdir -p /data/lancedb /data/cache /data/models

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command
ENTRYPOINT ["python", "src/cli/manage.py"]
CMD ["watch", "/app/codebase"]
