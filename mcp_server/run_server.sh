#!/bin/bash

echo "Starting MCP Server with filtered output..."
echo "Server will be available at the configured MCP_SERVER_URL"
echo ""

# Run the server and filter out the invalid HTTP request warnings
python main.py 2>&1 | grep -v "WARNING:  Invalid HTTP request received" | grep -v "WARNING: Unsupported upgrade request"