# MCP Server Deployment Guide

This guide documents the deployment of a FastMCP server behind nginx, including lessons learned and the correct configuration for Claude Desktop integration.

## Overview

The MCP (Model Context Protocol) server provides tools for Twitter data retrieval and web scraping. When deployed behind nginx, special care must be taken to ensure the SSE (Server-Sent Events) protocol works correctly with Claude Desktop.

## Key Lessons Learned

### 1. Path Rewriting Breaks MCP Protocol

**Problem**: Initial attempts used nginx path rewriting (e.g., `/mcp/sse` → `/sse`), which caused the MCP protocol to fail.

**Why it failed**:
- MCP server returns relative URLs in its SSE responses (e.g., `data: /messages/?session_id=xxx`)
- Claude Desktop receives these relative URLs and tries to resolve them relative to the original path
- With path rewriting, `/mcp/sse` + `/messages/` = `/mcp/messages/`, but the server expects just `/messages/`

**Solution**: Use direct proxying without path rewriting.

### 2. SSE Requires Special Nginx Configuration

Server-Sent Events need specific headers and settings to work properly through nginx:
- Disable buffering
- Set appropriate connection headers
- Configure long timeouts
- Remove cache headers

### 3. FastMCP Handles Tools Automatically

The server automatically responds to `tools/list` requests after initialization. No manual implementation needed - just ensure the tools are properly decorated with `@mcp.tool()`.

### 4. Environment Variables Don't Affect Client Connections

The `MCP_SERVER_URL` in `.env` is used for logging only. Claude Desktop gets its connection URL from its own configuration file, not from the server.

## Correct Nginx Configuration

Here's the working nginx configuration that properly proxies MCP/SSE traffic:

```nginx
server {
    server_name ava.reforge.vc;
    
    # Allow Let's Encrypt challenges
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Client max body size for file uploads
    client_max_body_size 50M;

    # Proxy to other applications (if any)
    location / {
        # Your main application proxy settings
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # CRITICAL: Direct SSE endpoint proxy (NO path rewriting!)
    location = /sse {
        proxy_pass http://127.0.0.1:8000/sse;
        proxy_http_version 1.1;
        
        # SSE-specific headers
        proxy_set_header Connection '';
        proxy_set_header Cache-Control 'no-cache';
        proxy_set_header X-Accel-Buffering 'no';
        
        # Disable buffering (critical for SSE)
        proxy_buffering off;
        proxy_cache off;
        
        # Long timeout for persistent connections
        proxy_read_timeout 24h;
        keepalive_timeout 24h;
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Direct SSE endpoint with trailing slash
    location = /sse/ {
        proxy_pass http://127.0.0.1:8000/sse/;
        proxy_http_version 1.1;
        
        # Same SSE configuration as above
        proxy_set_header Connection '';
        proxy_set_header Cache-Control 'no-cache';
        proxy_set_header X-Accel-Buffering 'no';
        
        proxy_buffering off;
        proxy_cache off;
        
        proxy_read_timeout 24h;
        keepalive_timeout 24h;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # CRITICAL: Direct messages endpoint proxy (NO path rewriting!)
    location ~ ^/messages/ {
        proxy_pass http://127.0.0.1:8000$request_uri;
        proxy_http_version 1.1;
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Content-Type $content_type;
    }
    
    # SSL configuration (managed by Certbot)
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/ava.reforge.vc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ava.reforge.vc/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

# HTTP to HTTPS redirect
server {
    if ($host = ava.reforge.vc) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    server_name ava.reforge.vc;
    return 404;
}
```

## Key Configuration Points

### 1. No Path Rewriting
- Use `proxy_pass http://127.0.0.1:8000/sse;` NOT `rewrite` directives
- Preserve the original URL structure that the MCP server expects

### 2. SSE-Specific Headers
```nginx
proxy_set_header Connection '';
proxy_set_header Cache-Control 'no-cache';
proxy_set_header X-Accel-Buffering 'no';
```

### 3. Disable Buffering
```nginx
proxy_buffering off;
proxy_cache off;
```

### 4. Long Timeouts
```nginx
proxy_read_timeout 24h;
keepalive_timeout 24h;
```

## Claude Desktop Configuration

Configure Claude Desktop to connect to your deployed server:

```json
{
  "mcpServers": {
    "openai-mcp": {
      "transport": "sse",
      "url": "https://ava.reforge.vc/sse/"
    }
  }
}
```

**Important**: Use the exact URL with trailing slash as shown above.

## Testing the Deployment

### 1. Test SSE Endpoint
```bash
curl -i https://ava.reforge.vc/sse/ -H "Accept: text/event-stream"
```

Expected response:
```
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: endpoint
data: /messages/?session_id=xxxxx
```

### 2. Test with MCP Inspector
1. Set transport to "SSE"
2. Enter URL: `https://ava.reforge.vc/sse/`
3. Click Connect
4. You should see the available tools listed

### 3. Verify in Claude Desktop
1. Open Claude Desktop settings
2. Add the MCP server configuration
3. Restart Claude Desktop
4. Check that tools are available in new conversations

## Troubleshooting

### "No tools available" in Claude Desktop
1. Ensure nginx is properly configured (no path rewriting)
2. Check that the MCP server is running
3. Verify the URL includes the trailing slash
4. Check server logs: `tail -f /home/ubuntu/mcp_server/openai_mcp/mcp_server/logs/mcp_server.log`

### 307 Redirects in logs
This indicates path rewriting is still active. Ensure you're using direct proxying as shown above.

### Connection timeouts
Check that SSE-specific headers and buffering settings are correctly configured.

## Why This Configuration Works

1. **Direct Proxying**: Mimics ngrok behavior by preserving URL paths
2. **SSE Support**: Proper headers and settings for Server-Sent Events
3. **Protocol Compliance**: Maintains the relative URL structure MCP expects
4. **No URL Translation**: Claude Desktop can correctly resolve all endpoints

## Alternative Approaches That Don't Work

1. **Path Rewriting** (`rewrite ^/mcp(/.*)$ $1 break;`) - Breaks relative URLs
2. **Subdirectory Mounting** (`location /mcp/`) - Causes URL resolution issues
3. **Missing SSE Headers** - Results in connection drops or buffering issues

## Summary

The key to successfully deploying FastMCP behind nginx is to:
1. Use direct proxying without path rewriting
2. Configure proper SSE headers and settings
3. Ensure both `/sse/` and `/messages/` endpoints are accessible
4. Use the root-level paths in Claude Desktop configuration

This setup ensures full compatibility with the MCP protocol while maintaining security and performance through nginx.