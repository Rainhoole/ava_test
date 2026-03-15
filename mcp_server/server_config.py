"""
Server configuration and middleware for MCP Server
"""

import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SSERequestFilter(BaseHTTPMiddleware):
    """Middleware to filter and handle non-SSE requests gracefully"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Log the request path for debugging (only in debug mode)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Incoming request: {request.method} {request.url.path}")
        
        # Handle health check endpoints
        if request.url.path in ["/health", "/", "/healthz"]:
            return Response(content="OK", status_code=200)
        
        # Handle favicon requests
        if request.url.path == "/favicon.ico":
            return Response(status_code=404)
        
        # For SSE endpoints, check if it's a proper SSE request
        if request.url.path == "/sse" or request.url.path.startswith("/sse/"):
            accept_header = request.headers.get("accept", "")
            if "text/event-stream" not in accept_header and request.method == "GET":
                # Log only once per unique client
                client_info = f"{request.client.host}:{request.client.port}" if request.client else "unknown"
                logger.debug(f"Non-SSE request from {client_info} - missing text/event-stream accept header")
        
        # Continue with the request
        response = await call_next(request)
        return response


def configure_logging():
    """Configure logging to reduce noise from invalid HTTP requests"""
    # Suppress specific loggers
    loggers_to_suppress = [
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "starlette.applications",
        "httpx",
        "httpcore"
    ]
    
    for logger_name in loggers_to_suppress:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # Set custom format for remaining logs
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Apply to root logger
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)


def suppress_invalid_request_warnings():
    """Additional configuration to suppress invalid request warnings"""
    import warnings
    import urllib3
    
    # Suppress urllib3 warnings
    urllib3.disable_warnings()
    
    # Suppress generic warnings
    warnings.filterwarnings("ignore", message=".*Invalid HTTP request received.*")
    warnings.filterwarnings("ignore", message=".*connection closed.*")
    warnings.filterwarnings("ignore", message=".*Unsupported upgrade request.*")