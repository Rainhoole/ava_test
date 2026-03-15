#!/usr/bin/env python3
"""
Firecrawl MCP Server for Claude Agent SDK.

Provides web scraping and search tools via Model Context Protocol.

Usage:
    # As MCP server (called by Claude Agent SDK)
    python firecrawl_mcp.py

    # Test mode
    python firecrawl_mcp.py --test https://example.com
"""

import os
import sys
import json
import re
import asyncio
import argparse
import logging
import tempfile
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv()

# Try to import mcp, provide helpful error if not installed
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

from docsend_extract import download_docsend_pdf

logger = logging.getLogger(__name__)


def _is_docsend_url(url: str) -> bool:
    """Check if URL is a DocSend document link."""
    return bool(re.match(r'https?://(www\.)?docsend\.com/view/', url))


def _extract_text_from_pdf_file(pdf_path: str) -> tuple[str, int]:
    """Extract text from a PDF file using pdfplumber. Returns (text, page_count)."""
    try:
        import pdfplumber

        pages_text = []
        page_count = 0
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"--- Page {i + 1} ---\n{text}")

        if pages_text:
            return "\n\n".join(pages_text), page_count

        return "[DocSend document contains image-based slides with no extractable text. The content appears to be a visual presentation/deck.]", page_count

    except ImportError:
        logger.warning("pdfplumber not installed, returning raw PDF info")
        return "[PDF text extraction unavailable — pdfplumber not installed]", 0
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return f"[PDF text extraction failed: {str(e)}]", 0


def _fetch_docsend_pdf(url: str, email: Optional[str] = None, passcode: Optional[str] = None) -> Optional[dict]:
    """Download a DocSend document as PDF and extract text.

    Uses docsend_extract module (DeckToPDF API primary, docsend2pdf.com fallback).
    Returns dict with 'content' (extracted text) and 'page_count', or None on failure.
    """
    try:
        logger.info(f"Fetching DocSend PDF: {url}")
        pdf_path = download_docsend_pdf(
            url=url,
            email=email,
            passcode=passcode or "",
        )

        if not pdf_path:
            return {"error": "DocSend PDF download failed (all services)", "url": url}

        pdf_size = os.path.getsize(pdf_path)
        text_content, page_count = _extract_text_from_pdf_file(pdf_path)

        return {
            "url": url,
            "content": text_content,
            "page_count": page_count,
            "pdf_size_bytes": pdf_size,
            "source": "docsend_extract",
        }

    except Exception as e:
        logger.error(f"DocSend fetch failed: {e}")
        return {"error": f"DocSend fetch failed: {str(e)}", "url": url}


class FirecrawlAPI:
    """Web scraping client using Firecrawl API."""

    def __init__(self):
        self.api_key = os.getenv('FIRECRAWL_API_KEY')
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY environment variable not set")

        from firecrawl import FirecrawlApp
        self.app = FirecrawlApp(api_key=self.api_key)

    def scrape_website(self, url: str, max_length: int = 80000) -> dict:
        """Scrape content from a URL.

        Args:
            url: The URL to scrape
            max_length: Maximum content length (default 80KB to save tokens)
        """
        # DocSend URLs need special handling — Firecrawl can't extract their content
        if _is_docsend_url(url):
            result = _fetch_docsend_pdf(url)
            if result and "error" not in result:
                content = result.get("content", "")
                if len(content) > max_length:
                    content = content[:max_length] + "\n\n[TRUNCATED]"
                return {
                    "url": url,
                    "content": f"# DocSend Document\n\nSource: {url}\nPages: {result.get('page_count', 'unknown')}\n\n{content}",
                    "original_length": len(result.get("content", "")),
                    "truncated_length": len(content),
                    "links": [],
                    "source": "docsend2pdf",
                }
            # If DocSend extraction failed, return the error
            if result and "error" in result:
                return result
            # Fall through to Firecrawl as last resort

        try:
            # Use scrape() method (not scrape_url)
            result = self.app.scrape(
                url,
                formats=['markdown'],
                only_main_content=True,
                timeout=50000
            )

            if not result:
                return {"error": "No content returned", "url": url}

            # Handle different result formats
            content = None
            if isinstance(result, dict):
                content = result.get('markdown') or result.get('html') or result.get('content')
            elif hasattr(result, 'markdown') and result.markdown:
                content = result.markdown
            elif hasattr(result, 'html') and result.html:
                content = result.html

            if not content:
                return {"error": "Could not extract content", "url": url}

            # Remove base64 images to save tokens
            content = re.sub(r'!\[.*?\]\(data:image\/[^)]+\)', '[IMAGE]', content)

            # Remove excessive whitespace
            content = re.sub(r'\n{3,}', '\n\n', content)

            # Truncate to max length
            original_length = len(content)
            if len(content) > max_length:
                content = content[:max_length] + "\n\n[TRUNCATED]"

            # Extract links from the page
            links = []
            if isinstance(result, dict) and result.get('links'):
                links = result['links'][:20]
            elif hasattr(result, 'links') and result.links:
                links = result.links[:20]

            return {
                "url": url,
                "content": content,
                "original_length": original_length,
                "truncated_length": len(content),
                "links": links
            }

        except Exception as e:
            return {"error": f"Failed to scrape: {str(e)}", "url": url}

    def search_web(self, query: str, limit: int = 5) -> dict:
        """Search the web and return results with content.

        Args:
            query: Search query
            limit: Maximum number of results (default 5)
        """
        try:
            result = self.app.search(
                query,
                limit=min(limit, 5)
            )

            if not result:
                return {"query": query, "results": [], "total": 0}

            # Handle different result formats
            data = []
            if isinstance(result, dict):
                data = result.get('data', []) or result.get('results', [])
            elif hasattr(result, 'data') and result.data:
                data = result.data
            elif isinstance(result, list):
                data = result

            if not data:
                return {"query": query, "results": [], "total": 0}

            results = []
            for item in data:
                if isinstance(item, dict):
                    content = item.get('markdown', '') or item.get('content', '') or item.get('snippet', '')
                else:
                    content = getattr(item, 'markdown', '') or getattr(item, 'content', '') or ''

                # Truncate each result to save tokens
                if len(content) > 15000:
                    content = content[:15000] + "\n\n[TRUNCATED]"

                title = item.get('title', '') if isinstance(item, dict) else getattr(item, 'title', '')
                url = item.get('url', '') if isinstance(item, dict) else getattr(item, 'url', '')

                results.append({
                    "title": title,
                    "url": url,
                    "content": content
                })

            return {
                "query": query,
                "total": len(results),
                "results": results
            }

        except Exception as e:
            return {"error": f"Failed to search: {str(e)}", "query": query}


# Create MCP server
server = Server("firecrawl-web")

# Initialize Firecrawl API (lazy loading)
_firecrawl_api = None


def get_firecrawl_api() -> FirecrawlAPI:
    global _firecrawl_api
    if _firecrawl_api is None:
        _firecrawl_api = FirecrawlAPI()
    return _firecrawl_api


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Firecrawl tools."""
    return [
        Tool(
            name="scrape_website",
            description="""Scrape and extract content from a website URL.

Use this to:
- Get full content from project websites, documentation, whitepapers
- Extract links to other important pages
- Scrape GitHub repos, blog posts, product pages

Returns markdown content (truncated to 80KB to save tokens) and discovered links.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to scrape"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum content length in chars (default: 80000)",
                        "default": 80000
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="search_web",
            description="""Search the web for information and return results with content.

Use this as LAST RESORT after exhausting primary sources (Twitter, website scraping).

Good for:
- Finding funding/investment news
- Discovering team background info
- Getting third-party coverage and reviews
- Filling specific information gaps

Keep queries concise (1-6 words) for best results.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keep concise, 1-6 words)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5, max: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Firecrawl tool."""
    try:
        firecrawl = get_firecrawl_api()

        if name == "scrape_website":
            result = firecrawl.scrape_website(
                arguments.get("url", ""),
                arguments.get("max_length", 80000)
            )

        elif name == "search_web":
            result = firecrawl.search_web(
                arguments.get("query", ""),
                arguments.get("limit", 5)
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def test_mode(url: str):
    """Test Firecrawl API directly."""
    print(f"Testing Firecrawl API")
    print("=" * 50)

    try:
        firecrawl = get_firecrawl_api()

        print(f"\n1. Scraping URL: {url}")
        result = firecrawl.scrape_website(url, max_length=5000)
        print(f"Content length: {result.get('truncated_length', 0)} chars")
        print(f"Links found: {len(result.get('links', []))}")
        if 'content' in result:
            print(f"Preview: {result['content'][:500]}...")

        print("\n2. Testing search...")
        search_result = firecrawl.search_web("blockchain AI infrastructure", limit=2)
        print(f"Results found: {search_result.get('total', 0)}")
        for r in search_result.get('results', []):
            print(f"  - {r.get('title', 'No title')}: {r.get('url', '')}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Firecrawl MCP Server")
    parser.add_argument("--test", type=str, help="Test mode: provide URL to scrape")
    args = parser.parse_args()

    if args.test:
        test_mode(args.test)
    else:
        # Run as MCP server
        asyncio.run(run_server())
