# Dockerfile for the Todoist Deep‑Research MCP connector
#
# This container builds a minimal environment to run the Python
# server defined in `todoist_mcp.py`. It installs only the
# dependencies listed in requirements.txt and exposes the
# appropriate port for Fly.io to proxy. The default entrypoint
# launches the FastMCP app via Python.

FROM python:3.11-slim AS base

# Work in a dedicated directory inside the container
WORKDIR /app

# Install system packages needed for building wheels (optional)
RUN apt-get update -qq && \
    apt-get install --no-install-recommends -y build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency specification into the image early so Docker
# can cache the pip install layer. If you add or change
# dependencies in requirements.txt, this layer will be invalidated.
COPY requirements.txt ./

# Install Python dependencies. The `--no-cache-dir` flag prevents
# pip from caching packages inside the image, keeping it lean.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the remaining application files into the container.  This
# includes the main server script (`todoist_mcp.py`) and any other
# supporting files (README, etc.). If you add new source files,
# list them here or use `COPY . .` to include everything in the
# repository root.
COPY todoist_mcp.py ./
COPY README.md ./

# Expose the port that FastMCP binds to. Fly.io automatically
# assigns the external ports based on fly.toml, but declaring this
# helps with local development and self‑documentation.
EXPOSE 8000

# Set an environment variable so Python output is not buffered. This
# ensures logs appear in the correct order in Fly's log stream.
ENV PYTHONUNBUFFERED=1

# Start the server. The CMD is defined using the exec form so
# signals are properly forwarded to Python (important for Fly
# container lifecycle). If you change the filename, update this
# accordingly.
CMD ["python", "todoist_mcp.py"]