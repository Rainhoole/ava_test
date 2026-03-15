# OpenAI Deep Research MCP Server Setup Guide

## Current Status
The MCP server is running correctly and the SSE endpoint is functioning. The server follows the FastMCP SSE transport protocol:

1. Initial SSE connection to `/sse/` returns a session-specific endpoint
2. All MCP communication happens via POST to the returned endpoint

## Verified Working Configuration

### Server Details
- **SSE Endpoint**: `https://243d-2600-4041-798d-1b00-bdcb-3cab-a283-6ba0.ngrok-free.app/sse/`
- **Transport**: SSE (Server-Sent Events)
- **Protocol**: MCP with JSON-RPC 2.0

### How FastMCP SSE Works
1. Client connects to `/sse/` endpoint
2. Server responds with SSE stream containing:
   ```
   event: endpoint
   data: /messages/?session_id=<unique-session-id>
   ```
3. Client sends all MCP requests as POST to the session endpoint

### Test Connection
```bash
# 1. Test SSE endpoint (should return session endpoint)
curl -N -H "Accept: text/event-stream" https://243d-2600-4041-798d-1b00-bdcb-3cab-a283-6ba0.ngrok-free.app/sse/

# 2. Initialize MCP (use the endpoint from step 1)
curl -X POST https://243d-2600-4041-798d-1b00-bdcb-3cab-a283-6ba0.ngrok-free.app/messages/?session_id=<session-id> \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {"tools": {}}
    },
    "id": 1
  }'
```

## Configuration for OpenAI Deep Research

### MCP Server Configuration
```json
{
  "name": "Twitter & Web Tools",
  "url": "https://243d-2600-4041-798d-1b00-bdcb-3cab-a283-6ba0.ngrok-free.app/sse/",
  "transport": "sse",
  "description": "Twitter profile analysis and web scraping tools"
}
```

### Available Tools
1. **get_twitter_profile** - Get detailed Twitter profile information
2. **get_twitter_following** - Get accounts a user follows (with founder detection)
3. **get_twitter_tweets** - Get recent tweets with URL extraction
4. **bulk_get_twitter_profiles** - Get multiple profiles efficiently
5. **scrape_website** - Scrape website content as markdown
6. **search_web** - Search web with automatic content scraping

## Troubleshooting

### If you see "HTTP invalid request"
This usually means the client is not following the SSE protocol correctly. Ensure:
1. The URL ends with `/sse/` (with trailing slash)
2. The client connects with `Accept: text/event-stream` header
3. The client reads the initial SSE event to get the session endpoint
4. All MCP requests are sent to the session endpoint, not the SSE endpoint

### Server Logs
Monitor server logs with:
```bash
cd /mnt/c/Projects/openai_mcp/mcp_server
python main.py
```

### Testing Individual Tools
Use the test scripts:
```bash
python tests/run_all_tests.py
```

## Important Notes
- The ngrok URL changes when restarted, update accordingly
- The server requires API keys in `.env` file:
  - `RAPID_API_KEY` for Twitter tools
  - `FIRECRAWL_API_KEY` for web tools
- Maximum 5000 following limit for Twitter following tool
- Web content limited to 125KB to prevent token overflow