# MCP Server - Twitter & Web Tools

## Overview
This is the Model Context Protocol (MCP) server that provides Twitter data retrieval and web scraping tools via FastMCP with SSE transport.

## Features
- **Twitter Tools**:
  - `get_twitter_profile` - Fetch detailed profile information
  - `get_twitter_following` - Get user's following list
  - `get_twitter_tweets` - Retrieve recent tweets
  - `bulk_get_twitter_profiles` - Batch profile retrieval
  
- **Web Tools**:
  - `scrape_website` - Extract content from websites
  - `search_web` - Web search with content scraping

## Setup
```bash
cd mcp_server
pip install -r requirements.txt
```

## Configuration
Create a `.env` file with:
```
RAPID_API_KEY=xxx        # For Twitter API via RapidAPI
FIRECRAWL_API_KEY=xxx    # For web scraping via Firecrawl
```

## Running the Server
```bash
python main.py
```

The server will start on `http://localhost:8000/sse`

## Testing
```bash
python tests/run_all_tests.py
```

## API Documentation
The server exposes tools via the MCP protocol. Connect any MCP-compatible client to use the tools.