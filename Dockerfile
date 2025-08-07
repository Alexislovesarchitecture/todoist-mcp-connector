# Python slim for small image size
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional, kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy and install deps first for layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY todoist_mcp.py /app/todoist_mcp.py

# Fly sets PORT (internal 8080 by default). We just respect it.
CMD ["sh", "-c", "uvicorn todoist_mcp:app --host 0.0.0.0 --port ${PORT:-8080}"]