#!/bin/bash
# Health check script for MCP Server

# Check if the service is responding
response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://ava.reforge.vc/sse/ -H "Accept: text/event-stream")

if [ "$response" = "200" ]; then
    echo "MCP Server is healthy"
    exit 0
else
    echo "MCP Server health check failed (HTTP $response)"
    exit 1
fi