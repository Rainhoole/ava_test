#!/bin/bash
# Production startup script for MCP Server

# Set working directory
cd /home/ubuntu/mcp_server/openai_mcp/mcp_server

# Activate virtual environment
source venv/bin/activate

# Load environment variables (use source to handle spaces in values)
set -a
source ../.env
set +a

# Log startup
echo "Starting MCP Server at $(date)" >> logs/startup.log

# Start the server
exec python main.py