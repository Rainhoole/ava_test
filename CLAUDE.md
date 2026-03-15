# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides Twitter data retrieval and web scraping capabilities for OpenAI's Deep Research API. The server exposes 6 main tools via FastMCP with SSE transport.

## Key Commands

### Running the Server
```bash
# Start the MCP server (runs on port 8000)
python main.py
```

### Running Tests
```bash
# Run all tests with summary
python tests/run_all_tests.py

# Run individual tool tests
python tests/test_twitter_profile.py      # Twitter profile lookup
python tests/test_twitter_following.py     # Twitter following analysis
python tests/test_twitter_tweets.py        # Twitter tweet extraction
python tests/test_bulk_twitter.py          # Bulk Twitter profiles
python tests/test_web_scraping.py          # Web scraping
python tests/test_web_search.py            # Web search
```

### Installation
```bash
# Install all dependencies
pip install -r requirements.txt
```

## Architecture

### Core Files
- `main.py` - MCP server entry point using FastMCP framework
- `tools.py` - Implementation of all 6 tools (Twitter + Web)
- `api_test.py` - OpenAI API integration testing
- `.env` - API keys configuration (RAPID_API_KEY, FIRECRAWL_API_KEY)

### Tool Implementation Pattern
All tools in `tools.py` follow this pattern:
1. Input validation
2. API call with error handling
3. Response parsing and data extraction
4. Size optimization (125KB limit for web content)
5. Structured response formatting

### Twitter Tools (via RapidAPI)
- `get_twitter_profile` - Profile data with follower counts, bio, URLs
- `get_twitter_following` - Following list with founder detection logic
- `get_twitter_tweets` - Recent tweets with URL extraction from entities
- `bulk_get_twitter_profiles` - Efficient multi-profile fetching (max 100)

### Web Tools (via Firecrawl)
- `scrape_website` - Markdown content extraction with image removal
- `search_web` - Search with automatic content scraping

### Error Handling Strategy
- API failures return structured error messages
- Rate limits handled gracefully (skip users with >5000 following)
- Missing API keys provide clear instructions
- Network errors include retry guidance

### Testing Approach
- Each tool has dedicated test file
- Tests cover success cases, edge cases, and error conditions
- JSON logs saved for Twitter tweet tests
- All tests can be run individually or via master runner

## Development Guidelines

### Code Style (from .cursor/rules/general.mdc)
- Be terse and provide actual code, not high-level explanations
- Anticipate needs and suggest non-conventional solutions
- No moral lectures or unnecessary safety warnings
- Respect existing code formatting preferences

### API Key Management
Required environment variables in `.env`:
- `RAPID_API_KEY` - Twitter API access via RapidAPI
- `FIRECRAWL_API_KEY` - Web scraping/search via Firecrawl
- `OPENAI_API_KEY` - For API testing (optional)
- `MCP_SERVER_URL` - Server URL configuration

### Key Implementation Details
- FastMCP server with SSE transport on port 8000
- All responses optimized for AI consumption
- URL extraction includes expanded URLs from Twitter entities
- Founder detection based on following age (oldest_first parameter)
- Content size limits enforced (125KB for web scraping)
- Comprehensive error messages for debugging

### Testing Strategy
1. Always run `python tests/run_all_tests.py` after changes
2. Individual test files for focused debugging
3. Test data logs help verify Twitter API responses
4. Edge cases include rate limits, invalid inputs, API failures

### Integration Points
- Primary: OpenAI Deep Research API
- Secondary: Gemini API (see api_test_gemini_native.py)
- Transport: Server-Sent Events (SSE) via FastMCP
- Data sources: RapidAPI (Twitter), Firecrawl (Web)