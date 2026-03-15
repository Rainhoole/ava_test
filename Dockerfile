# Railway Dockerfile for Research Agent Web Server
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (required for Claude Code CLI)
RUN useradd -m -s /bin/bash appuser

# Copy requirements first for better caching
COPY requirements.txt .
COPY research_agent_cowork/requirements.txt ./research_agent_cowork_requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r research_agent_cowork_requirements.txt

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /app/research_agent_cowork/outputs && \
    chown -R appuser:appuser /app

# Expose the port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Switch to non-root user
USER appuser

# Set working directory to research_agent_cowork
WORKDIR /app/research_agent_cowork

# Run the Research Agent Web Server (MCP is mounted in-process)
CMD ["python", "web_server.py"]
