FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (better caching), with a pip upgrade
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY todoist_mcp.py /app/todoist_mcp.py

# Run ASGI server on Fly's PORT (internal 8080)
CMD ["sh", "-c", "uvicorn todoist_mcp:app --host 0.0.0.0 --port ${PORT:-8080}"]