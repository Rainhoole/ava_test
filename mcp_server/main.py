#!/usr/bin/env python3
"""
OpenAI MCP Server with Twitter and Web Tools

This server implements the Model Context Protocol (MCP) with comprehensive tools
for Twitter data retrieval and web scraping/search using real APIs.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, List
from urllib.parse import urlparse
from dotenv import load_dotenv
from fastmcp import FastMCP
from tools import Tools
import json
import datetime
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

# Load environment variables
load_dotenv('../.env')  # Load from parent directory
load_dotenv()  # Also try current directory

# Configure logging with custom filter
class InvalidHTTPFilter(logging.Filter):
    def filter(self, record):
        msg = str(record.getMessage())
        # Filter out the invalid HTTP request warnings
        if "Invalid HTTP request received" in msg:
            return False
        if "Unsupported upgrade request" in msg:
            return False
        # Filter out ASGI shutdown exceptions
        if "Exception in ASGI application" in msg:
            return False
        if "Expected ASGI message" in msg:
            return False
        if "Cancel 0 running task" in msg:
            return False
        if "RuntimeError" in msg and "http.response" in msg:
            return False
        return True

# Configure file-based logging with rotation
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Create a rotating file handler
log_file = os.path.join(log_dir, 'mcp_server.log')
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB per file
    backupCount=5,  # Keep 5 backup files
    encoding='utf-8'
)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)

# Configure console handler with simpler format
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
console_handler.addFilter(InvalidHTTPFilter())

# Apply the filter to root logger
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
root_logger = logging.getLogger()
root_logger.addFilter(InvalidHTTPFilter())

logger = logging.getLogger(__name__)

# Suppress all the noisy HTTP warnings
import warnings
warnings.filterwarnings("ignore", message=".*Invalid HTTP request received.*")

# Suppress uvicorn and ASGI server warnings
logging.getLogger("uvicorn").setLevel(logging.ERROR)
logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
logging.getLogger("uvicorn.protocols").setLevel(logging.ERROR)
logging.getLogger("uvicorn.protocols.http").setLevel(logging.ERROR)
logging.getLogger("uvicorn.protocols.http.h11_impl").setLevel(logging.ERROR)
logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.ERROR)
logging.getLogger("uvicorn.lifespan").setLevel(logging.ERROR)
logging.getLogger("uvicorn.lifespan.on").setLevel(logging.ERROR)

# Also suppress httptools and h11 parsers
logging.getLogger("httptools").setLevel(logging.ERROR)
logging.getLogger("h11").setLevel(logging.ERROR)

# Import server configuration
try:
    from server_config import configure_logging, suppress_invalid_request_warnings
    configure_logging()
    suppress_invalid_request_warnings()
except ImportError:
    pass  # Server config is optional


def create_server():
    """Create and configure the MCP server with all Twitter and web tools."""

    # Initialize the FastMCP server
    mcp = FastMCP(name="OpenAI MCP Tools Server",
                  instructions="""
        This MCP server provides comprehensive Twitter data retrieval and web scraping capabilities.
        
        Available Tools:
        - get_twitter_profile: Get detailed Twitter profile information
        - get_twitter_following: Get accounts a user follows (newest to oldest detection)
        - get_twitter_tweets: Get recent tweets from a user (with URL extraction)
        - bulk_get_twitter_profiles: Get multiple Twitter profiles efficiently
        - scrape_website: Scrape content from any website
        
        Use these tools to gather comprehensive information about Twitter users,
        their networks, content, and related web resources.
        """)

    # Initialize the tools instance
    tools_instance = Tools()

    @mcp.tool()
    async def get_twitter_profile(username: str) -> Dict[str, Any]:
        """
        Get detailed profile information for a Twitter user by their username.
        
        Args:
            username: Twitter username (with or without @ symbol)
            
        Returns:
            Dictionary containing comprehensive profile information including:
            - Basic info (name, bio, location)
            - Follower/following counts
            - Verification status
            - Profile URLs and creation date
            (~1K tokens per profile)
        """
        logger.info(f"Tool 'get_twitter_profile' called with args: username={username}")
        result = tools_instance.get_twitter_profile(username)
        logger.info(f"Profile fetch {'successful' if 'error' not in result else 'failed'} for @{username}")
        return result

    @mcp.tool()
    async def get_twitter_following(username: str, oldest_first: bool = False) -> Dict[str, Any]:
        """
        Fetch profiles of accounts that the target user is following.
        
        Args:
            username: Twitter username to analyze
            oldest_first: If True, returns oldest 50 followings (potential founders/early team)
            
        Returns:
            Dictionary containing following profiles with founder detection capabilities.
            Automatically skips users following >5000 accounts to avoid rate limits.
        """
        logger.info(f"Tool 'get_twitter_following' called with args: username={username}, oldest_first={oldest_first}")
        result = tools_instance.get_twitter_following(username, oldest_first)
        logger.info(f"Following fetch {'successful' if 'error' not in result else 'failed'} for @{username}")
        return result

    @mcp.tool()
    async def get_twitter_tweets(username: str, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch recent tweets posted by a Twitter user with comprehensive data extraction.
        
        Args:
            username: Twitter username to get tweets from
            limit: Number of tweets to fetch (default 20, ~10K tokens)
            
        Returns:
            Dictionary containing tweet entries with:
            - Full text content (including note tweets with proper flattening)
            - Engagement metrics (likes, retweets, replies, quotes)
            - Extracted URLs from tweet entities (including media URLs)
            - Tweet metadata and timestamps
            - Note tweet specific data when applicable (note_tweet_id, note_tweet_entities, etc.)
            - Regular tweet entities and media when applicable
        """
        logger.info(f"Tool 'get_twitter_tweets' called with args: username={username}, limit={limit}")
        result = tools_instance.get_twitter_tweets(username, limit)
        logger.info(f"Tweet fetch {'successful' if 'error' not in result else 'failed'} for @{username}")
        return result

    @mcp.tool()
    async def bulk_get_twitter_profiles(identifiers: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch profiles for multiple Twitter users by username.
        
        Args:
            identifiers: List of Twitter usernames (max 20)
            
        Returns:
            List of profile dicts as returned by `get_twitter_profile`.
        """
        logger.info(f"Tool 'bulk_get_twitter_profiles' called with args: {len(identifiers)} identifiers")
        result = tools_instance.bulk_get_twitter_profiles(identifiers)
        logger.info(f"Bulk profile fetch completed: {len(result)} results returned")
        return result

    @mcp.tool()
    async def scrape_website(url: str, include_links: bool = False) -> str:
        """
        Scrape content from a website and return clean text.
        
        Args:
            url: The URL to scrape
            include_links: Optional parameter (stub - ignored, links are always included in response)
            
        Returns:
            String containing the scraped content in markdown format,
            with images removed and content size limited to 125KB.
            WARNING: Can return up to 32K tokens per site.
        """
        logger.info(f"Tool 'scrape_website' called with args: url={url}, include_links={include_links}")
        # Note: include_links parameter is ignored - the response always includes links if available
        result = tools_instance.scrape_website(url)
        logger.info(f"Website scrape {'successful' if 'error' not in result else 'failed'} for {url}")
        return result

    # @mcp.tool()
    # async def search_web(query: str, limit: int = 5) -> Dict[str, Any]:
    #     """
    #     Search the web for information with automatic content scraping.
    #     
    #     Args:
    #         query: Search query string
    #         limit: Number of search results to return (default 5, max 10)
    #         
    #     Returns:
    #         Dictionary containing search results with:
    #         - Scraped content from each result (~5-10K tokens)
    #         - Combined content for easy analysis
    #         - Individual result metadata
    #         - Links and structured data
    #         WARNING: Total can be 25-50K tokens with 5 results
    #     """
    #     logger.info(f"Searching web for: '{query}' (limit: {limit})")
    #     result = tools_instance.search_web(query, limit)
    #     logger.info(f"Web search {'successful' if 'error' not in result else 'failed'} for query: {query}")
    #     return result

    return mcp


async def health_check(request):
    """Health check endpoint for Railway/Docker health checks."""
    return JSONResponse({
        "status": "healthy",
        "service": "mcp-server",
        "timestamp": datetime.datetime.now().isoformat()
    })


def main():
    """Main function to start the MCP server."""
    logger.info("="*60)
    logger.info(f"Starting MCP Server - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    logger.info("Creating OpenAI MCP Tools Server...")

    # Get MCP_SERVER_URL from environment
    mcp_server_url = os.environ.get("MCP_SERVER_URL", "http://0.0.0.0:8000/sse")
    logger.info(f"MCP_SERVER_URL from environment: {mcp_server_url}")
    
    # Parse the URL to extract host and port
    parsed_url = urlparse(mcp_server_url)
    
    # Extract host and port with defaults
    if parsed_url.hostname:
        # For ngrok URLs or external URLs, bind to 0.0.0.0 to accept connections
        host = "0.0.0.0"
        logger.info(f"Detected external URL ({parsed_url.hostname}), binding to 0.0.0.0")
    else:
        host = "0.0.0.0"
    
    # Extract port - Railway sets PORT env var, fallback to URL port or 8000
    railway_port = os.environ.get("PORT")
    if railway_port:
        port = int(railway_port)
        logger.info(f"Using Railway PORT environment variable: {port}")
    else:
        port = parsed_url.port if parsed_url.port else 8000
    
    # Log the configuration
    logger.info(f"Server Configuration:")
    logger.info(f"  - MCP_SERVER_URL: {mcp_server_url}")
    logger.info(f"  - Binding to: {host}:{port}")
    logger.info(f"  - Transport: SSE")
    
    # Create the MCP server
    server = create_server()

    # Add health check route for Railway/Docker
    # FastMCP uses Starlette under the hood, we can add custom routes
    try:
        from starlette.routing import Route
        health_route = Route("/health", health_check)
        if hasattr(server, '_app') and server._app:
            server._app.routes.append(health_route)
        elif hasattr(server, 'app') and server.app:
            server.app.routes.append(health_route)
    except Exception as e:
        logger.warning(f"Could not add health check route: {e}")

    # Configure and start the server
    logger.info(f"Starting MCP server on {host}:{port} (accessible via {mcp_server_url})")
    logger.info("Server provides Twitter data retrieval and web scraping tools")
    logger.info("Connect this server to OpenAI Deep Research for comprehensive analysis")
    logger.info(f"Log file location: {log_file}")
    logger.info("")

    # Handle graceful shutdown
    import signal
    import sys
    import asyncio
    
    def signal_handler(sig, frame):
        logger.info("\nGracefully shutting down...")
        # Set a flag instead of trying to cancel tasks directly
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Use FastMCP's built-in run method with SSE transport
        server.run(transport="sse", host=host, port=port)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Server stopped by user")
    except asyncio.CancelledError:
        logger.info("Server tasks cancelled")
    except Exception as e:
        # Only log real errors, not shutdown-related ones
        if "CancelledError" not in str(type(e)) and "Expected ASGI message" not in str(e):
            logger.error(f"Server error: {e}")
    finally:
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error in main:")
        raise 
