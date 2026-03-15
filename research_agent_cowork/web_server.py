#!/usr/bin/env python3
"""
Research Agent Web Server.

FastAPI server providing REST API for research agent operations.

Usage:
    # Start with default version (v3)
    python web_server.py

    # Start with specific version
    python web_server.py --version v1
    python web_server.py --version v3

    # Specify port
    python web_server.py --port 8080
"""

import os
import sys
import asyncio
import argparse
import logging
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import aiofiles

from task_manager import TaskManager, TaskStatus, Task, PaymentStatus
from agent_runner import get_agent_runner, AgentRunnerOpenAI, AgentResult
from firecrawl_mcp import FirecrawlAPI
from fluxa_payment import get_payment_service, FluxaPaymentService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global configuration
class ServerConfig:
    version: str = "v3"
    model: str = "claude-opus-4-5-20251101"
    port: int = 8000

config = ServerConfig()
task_manager: Optional[TaskManager] = None
firecrawl_api: Optional[FirecrawlAPI] = None

def _extract_bearer_token(request: Request, jwt_param: Optional[str] = None) -> str:
    """Extract bearer token from Authorization header or query param."""
    if jwt_param:
        return jwt_param

    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    return parts[1]


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT format")
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload_b64 += padding
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        return json.loads(payload_json)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authorization token")


def _extract_client_id(payload: dict) -> Optional[str]:
    for key in ("agent_id", "agentId", "sub", "user_id", "uid", "id"):
        value = payload.get(key)
        if value:
            return str(value)

    agent_info = payload.get("agent") or payload.get("agent_info")
    if isinstance(agent_info, dict):
        for key in ("agent_id", "agentId", "id"):
            value = agent_info.get(key)
            if value:
                return str(value)

    return None


def require_auth(request: Request, jwt_param: Optional[str] = None) -> tuple[str, str]:
    """Require authorization and return (client_id, jwt)."""
    jwt = _extract_bearer_token(request, jwt_param)
    payload = _decode_jwt_payload(jwt)
    client_id = _extract_client_id(payload)
    if not client_id:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    return client_id, jwt


def require_client_id(request: Request, jwt_param: Optional[str] = None) -> str:
    """Require a client identifier for request scoping."""
    client_id, _ = require_auth(request, jwt_param)
    return client_id


def ensure_task_owner(task: Task, client_id: str):
    """Ensure a task belongs to the requesting client."""
    if not task.client_id or task.client_id != client_id:
        raise HTTPException(status_code=404, detail="Task not found")


# Pydantic models
class ResearchRequest(BaseModel):
    handle: str = Field(..., description="Research target: Twitter handle (e.g., @username), URL, or PDF URL")
    engine: str = Field("openai", description="Engine to use: 'openai'")
    model: Optional[str] = Field(None, description="Model override (e.g., 'gpt-5.2-2025-12-11', 'claude-opus-4-5-20251101')")
    mandate_id: str = Field(..., description="Fluxa mandate ID for payment authorization (required)")
    budget_usd: float = Field(2.0, description="Research budget in USD (default: $2.00)")
    fluxa_jwt: Optional[str] = Field(None, description="Fluxa JWT for payment processing")
    instant: bool = Field(True, description="Use instant processing (disable flex, faster but more expensive)")


class TaskResponse(BaseModel):
    task_id: str
    handle: str
    status: str
    version: str
    engine: str = "openai"
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    message_count: int = 0
    cost_usd: float = 0.0
    error_message: Optional[str] = None
    # Payment fields
    mandate_id: Optional[str] = None
    budget_usd: float = 2.0
    payment_status: str = "pending"
    payment_amount_usd: float = 0.0
    tool_calls: int = 0
    payment_error: Optional[str] = None
    payment_tx_hash: Optional[str] = None
    # Structured failure fields
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    retryable: Optional[bool] = None
    upstream_request_id: Optional[str] = None


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int


class ReportResponse(BaseModel):
    task_id: str
    handle: str
    status: str
    report: Optional[dict] = None


class ConfigResponse(BaseModel):
    version: str
    model: str
    available_versions: List[str] = ["v1", "v3"]
    available_engines: List[str] = ["openai"]


class WebFetchRequest(BaseModel):
    url: str = Field(..., description="URL to scrape")
    max_length: int = Field(80000, description="Maximum content length in chars")


class WebFetchResponse(BaseModel):
    url: str
    content: Optional[str] = None
    original_length: Optional[int] = None
    truncated_length: Optional[int] = None
    links: Optional[List[str]] = None
    error: Optional[str] = None


class PaymentDetailsResponse(BaseModel):
    task_id: str
    payment_status: str
    budget_usd: float
    claude_cost_usd: float
    tool_calls: int
    tool_cost_usd: float
    total_cost_usd: float
    payment_amount_usd: float
    payment_tx_hash: Optional[str] = None
    payment_error: Optional[str] = None


class RetryPaymentRequest(BaseModel):
    fluxa_jwt: Optional[str] = Field(None, description="Fresh Fluxa JWT (optional, falls back to stored JWT)")
    mandate_id: Optional[str] = Field(None, description="New mandate ID (required if old mandate is expired/exhausted)")


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global task_manager

    # Startup
    logger.info(f"Starting Research Agent Web Server")
    logger.info(f"Version: {config.version}")
    logger.info(f"Model: {config.model}")

    # Initialize task manager
    db_path = Path(__file__).parent / "tasks.db"
    output_base = Path(__file__).parent / "outputs"
    task_manager = TaskManager(str(db_path), str(output_base))
    await task_manager.init()

    logger.info(f"Task database initialized: {db_path}")

    # Sync historical tasks from remote bucket (for redeployment recovery)
    try:
        synced = await task_manager.sync_tasks_from_remote(download_files=True)
        if synced > 0:
            logger.info(f"Restored {synced} historical tasks from bucket storage")
    except Exception as e:
        logger.warning(f"Failed to sync tasks from remote (non-critical): {e}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if task_manager:
        await task_manager.close()


# Create FastAPI app
app = FastAPI(
    title="Research Agent API",
    description="VC Research Agent Web Server - Analyze Twitter profiles for investment potential",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== MCP Server (in-process) ==============

_mcp_mount_status = {"ok": False, "error": None}


def _create_and_mount_mcp():
    """
    Create MCP server and mount SSE endpoints into FastAPI.

    Uses Starlette Routes (verified working: GET /mcp/sse returned 200 in
    production) with the low-level mcp SDK SseServerTransport.
    """
    global _mcp_mount_status
    try:
        # Add mcp_server directory to path so its internal imports work
        mcp_dir = str(Path(__file__).parent.parent / "mcp_server")
        if mcp_dir not in sys.path:
            sys.path.insert(0, mcp_dir)

        logger.info(f"[MCP] Importing MCP server from {mcp_dir}")

        from main import create_server as create_mcp_server
        from mcp.server.sse import SseServerTransport
        from starlette.routing import Route
        from starlette.applications import Starlette

        logger.info("[MCP] Imports OK, creating MCP server instance")
        mcp_instance = create_mcp_server()

        # Access the underlying mcp.server.Server for the SSE transport
        mcp_server = mcp_instance._mcp_server
        logger.info(f"[MCP] Low-level MCP server: {type(mcp_server)}")

        # Path "/messages/" is RELATIVE to the mount point.
        # Mounted at /mcp → SSE event sends "data: /messages/?sessionId=xxx"
        # → OpenAI resolves relative to SSE base /mcp/ → POST /mcp/messages/
        # → Mount strips /mcp → sub-app sees /messages/ → route matches.
        sse_transport = SseServerTransport("/messages/")

        # Define handlers as raw ASGI apps (scope, receive, send) instead of
        # Starlette endpoints.  Starlette's request_response() wrapper expects
        # endpoints to *return* a Response; the MCP SSE transport handles the
        # ASGI send channel directly and returns None, which caused:
        #   TypeError: 'NoneType' object is not callable
        async def _handle_sse(scope, receive, send):
            logger.info("[MCP] SSE connection established")
            async with sse_transport.connect_sse(
                scope, receive, send
            ) as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options(),
                )

        async def _handle_messages(scope, receive, send):
            await sse_transport.handle_post_message(
                scope, receive, send
            )

        # Build routes then replace .app with raw ASGI handlers so that
        # Starlette does NOT wrap them with request_response().
        sse_route = Route("/sse", endpoint=lambda r: None)
        sse_route.app = _handle_sse

        msg_route = Route("/messages/", endpoint=lambda r: None, methods=["POST"])
        msg_route.app = _handle_messages

        mcp_starlette = Starlette(routes=[sse_route, msg_route])
        app.mount("/mcp", mcp_starlette, name="mcp_server")

        _mcp_mount_status = {"ok": True, "error": None}
        logger.info("[MCP] MCP server mounted at /mcp/sse (in-process, SseServerTransport)")
    except Exception as e:
        _mcp_mount_status = {"ok": False, "error": str(e)}
        logger.error(f"[MCP] FAILED to mount MCP server: {e}")
        import traceback
        traceback.print_exc()


_create_and_mount_mcp()


import re

def classify_failure(error: str) -> tuple:
    """Classify an error into (failure_stage, failure_code, retryable)."""
    err_lower = error.lower() if error else ""

    # Provider auth issues
    if any(k in err_lower for k in ("api_key not set", "api key not set", "api_key not configured")):
        return ("provider_auth", "provider_key_missing", False)
    if any(k in err_lower for k in ("401", "unauthorized", "invalid api key", "invalid_api_key", "authentication")):
        return ("provider_auth", "provider_auth_failed", False)

    # Provider quota / billing
    if any(k in err_lower for k in ("credit balance is too low", "insufficient_quota", "billing", "quota exceeded")):
        return ("provider_quota", "billing_insufficient_credit", False)

    # Rate limiting
    if any(k in err_lower for k in ("429", "rate limit", "rate_limit", "too many requests")):
        return ("provider_runtime", "provider_rate_limited", True)

    # Provider runtime / internal errors
    if any(k in err_lower for k in ("500", "502", "503", "504", "internal server error", "an error occurred while processing")):
        return ("provider_runtime", "provider_internal_error", True)
    if any(k in err_lower for k in ("timeout", "timed out", "connection error", "connection refused", "connect timeout")):
        return ("provider_runtime", "provider_timeout", True)

    # Tool / MCP errors
    if any(k in err_lower for k in ("mcp", "tool_runtime", "tool execution", "tool failed")):
        return ("tool_runtime", "tool_execution_failed", True)

    # No output from provider
    if "no output" in err_lower:
        return ("provider_runtime", "provider_no_output", True)

    # Default: internal
    return ("internal", "internal_error", False)


def _extract_upstream_request_id(error: str) -> Optional[str]:
    """Extract OpenAI request ID (req_xxx) from error message."""
    if not error:
        return None
    match = re.search(r'(req_[a-zA-Z0-9]+)', error)
    return match.group(1) if match else None


# Background task runner
async def run_research_task(task_id: str):
    """Run research task in background."""
    global task_manager

    logger.info(f"[BG] Starting background task: {task_id}")

    task = await task_manager.get_task(task_id)
    if not task:
        logger.error(f"[BG] Task not found: {task_id}")
        return

    tool_call_count = 0  # Track tool calls for payment calculation

    try:
        # Update status to running
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING)
        logger.info(f"[BG] Task status updated to RUNNING: {task_id}")

        # Ensure output directory exists
        output_dir = Path(task.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[BG] Output dir: {output_dir}")

        # Get agent runner (OpenAI only)
        model = task.version if (task.version and (task.version.startswith("gpt") or task.version.startswith("o"))) else "gpt-5.2-2025-12-11"
        use_flex = not task.instant
        logger.info(f"[BG] Task engine=openai, model={model}")
        runner = AgentRunnerOpenAI(model=model, use_flex=use_flex)
        logger.info(f"[BG] Agent runner initialized: {runner.__class__.__name__}")

        # Progress callback with actual tool call tracking from runner
        async def progress_callback(message_count: int, cost_usd: float, actual_tool_calls: int):
            nonlocal tool_call_count
            tool_call_count = actual_tool_calls
            await task_manager.update_task_progress(task_id, message_count, cost_usd, tool_call_count)

        # Run agent
        result = await runner.run(
            handle=task.handle,
            output_dir=Path(task.output_dir),
            log_file=Path(task.log_file),
            report_file=Path(task.report_file),
            progress_callback=progress_callback,
            upload_file=task.upload_file
        )

        if result.success:
            # Use authoritative tool call count from runner
            tool_call_count = result.tool_call_count
            # Update task progress
            await task_manager.update_task_progress(
                task_id, result.message_count, result.cost_usd, tool_call_count
            )
            if result.report_file:
                await task_manager.update_task_files(
                    task_id, report_file=result.report_file
                )

            # Process payment (mandate is always required)
            await process_task_payment(task_id, task.mandate_id, task.fluxa_jwt, result.cost_usd, tool_call_count)

            # Update task status after payment processing
            await task_manager.update_task_status(task_id, TaskStatus.COMPLETED)

            # Update meta.json with completion stats
            task_manager.update_task_meta(
                task_id=task_id,
                handle=task.handle,
                status="completed",
                message_count=result.message_count,
                cost_usd=result.cost_usd,
                duration_seconds=result.duration_seconds if hasattr(result, 'duration_seconds') else None,
                completed_at=datetime.now().isoformat() + "Z"
            )

            logger.info(f"Task completed: {task_id}")
        else:
            stage, code, retry = classify_failure(result.error or "")
            req_id = _extract_upstream_request_id(result.error or "")
            await task_manager.update_task_status(
                task_id, TaskStatus.FAILED, error_message=result.error,
                failure_stage=stage, failure_code=code,
                retryable=retry, upstream_request_id=req_id
            )

            # Update meta.json with failure info
            task_manager.update_task_meta(
                task_id=task_id,
                handle=task.handle,
                status="failed",
                error=result.error,
                completed_at=datetime.now().isoformat() + "Z"
            )

            logger.error(f"Task failed: {task_id} - stage={stage} code={code} retryable={retry} req_id={req_id} - {result.error}")

    except asyncio.CancelledError:
        await task_manager.update_task_status(task_id, TaskStatus.CANCELLED)
        task_manager.update_task_meta(
            task_id=task_id,
            handle=task.handle,
            status="cancelled",
            completed_at=datetime.now().isoformat() + "Z"
        )
        logger.info(f"[BG] Task cancelled: {task_id}")
    except Exception as e:
        logger.error(f"[BG] Task error: {task_id} - {e}")
        import traceback
        traceback.print_exc()
        err_str = str(e)
        stage, code, retry = classify_failure(err_str)
        req_id = _extract_upstream_request_id(err_str)
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, error_message=err_str,
            failure_stage=stage, failure_code=code,
            retryable=retry, upstream_request_id=req_id
        )
        task_manager.update_task_meta(
            task_id=task_id,
            handle=task.handle,
            status="failed",
            error=err_str,
            completed_at=datetime.now().isoformat() + "Z"
        )
    finally:
        # Sync to remote storage for ALL terminal states (completed, failed, cancelled)
        try:
            sync_success = await task_manager.sync_task_to_remote(task_id)
            if sync_success:
                logger.info(f"Task files synced to remote: {task_id}")
            else:
                logger.debug(f"Remote sync skipped (not configured): {task_id}")
        except Exception as e:
            logger.warning(f"Remote sync failed (non-critical): {e}")

        task_manager.unregister_running_task(task_id)
        logger.info(f"[BG] Task finished: {task_id}")


async def process_task_payment(
    task_id: str,
    mandate_id: str,
    fluxa_jwt: Optional[str],
    claude_cost_usd: float,
    tool_calls: int
):
    """
    Process payment for a completed research task.

    Calculates total cost (Claude API + tool calls) and charges via Fluxa.
    Uses the fluxa_jwt from the frontend agent that created the mandate.
    """
    payment_service = get_payment_service()

    # Calculate total cost
    cost_breakdown = payment_service.calculate_task_cost(claude_cost_usd, tool_calls)
    total_cost = cost_breakdown["total_cost_usd"]

    logger.info(f"[PAY] Processing payment for task {task_id}: ${total_cost:.4f}")
    logger.info(f"[PAY] Breakdown - Claude: ${claude_cost_usd:.4f}, Tools: {tool_calls} x $0.01 = ${cost_breakdown['tool_cost_usd']:.4f}")

    # Update payment status to processing
    await task_manager.update_payment_status(task_id, PaymentStatus.PROCESSING)

    # Process the payment (use frontend JWT for x402 call)
    result = await payment_service.process_payment(
        mandate_id=mandate_id,
        amount_usd=total_cost,
        description=f"Research task {task_id}: Claude API + {tool_calls} tool calls",
        task_id=task_id,
        user_jwt=fluxa_jwt
    )

    if result.success:
        logger.info(f"[PAY] Payment successful for task {task_id}: tx={result.transaction_hash}")
        await task_manager.update_payment_status(
            task_id,
            PaymentStatus.COMPLETED,
            payment_amount_usd=total_cost,
            payment_tx_hash=result.transaction_hash
        )
    else:
        logger.error(f"[PAY] Payment failed for task {task_id}: {result.error}")
        await task_manager.update_payment_status(
            task_id,
            PaymentStatus.FAILED,
            payment_error=result.error
        )


# API Endpoints

@app.get("/", summary="Health check")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Research Agent API",
        "version": config.version,
        "model": config.model
    }


@app.get("/mcp-status", summary="MCP server mount status")
async def mcp_status():
    """Diagnostic endpoint showing whether MCP mounted successfully."""
    return {
        "mcp_mounted": _mcp_mount_status["ok"],
        "error": _mcp_mount_status["error"],
        "routes": [str(r.path) if hasattr(r, 'path') else str(r) for r in app.routes],
    }


@app.get("/config", response_model=ConfigResponse, summary="Get server configuration")
async def get_config():
    """Get current server configuration."""
    return ConfigResponse(
        version=config.version,
        model=config.model
    )


@app.post("/research", response_model=TaskResponse, summary="Submit research task")
async def create_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    http_request: Request
):
    """
    Submit a new research task.

    The task will run in the background using the configured agent version.
    Optionally include a mandate_id for payment processing.
    """
    logger.info(f"[API] POST /research: handle={request.handle}, engine={request.engine}, model={request.model}")

    # Check task_manager is initialized
    if task_manager is None:
        logger.error("task_manager is None!")
        raise HTTPException(status_code=500, detail="Server not initialized properly")

    try:
        client_id, auth_jwt = require_auth(http_request)

        # Validate handle / URL input
        handle = request.handle.strip()
        if not handle:
            raise HTTPException(status_code=400, detail="Handle cannot be empty")

        # Only add @ prefix for non-URL inputs
        is_url = handle.startswith('http://') or handle.startswith('https://')
        if not is_url and not handle.startswith('@'):
            handle = f"@{handle}"

        # DocSend URLs: download PDF and treat as file upload for native OpenAI PDF reading
        upload_file_path = None
        if is_url and re.match(r'https?://(www\.)?docsend\.com/view/', handle):
            logger.info(f"[API] DocSend URL detected, downloading PDF: {handle}")
            try:
                from docsend_extract import download_docsend_pdf
                pdf_path = download_docsend_pdf(
                    url=handle,
                    output_dir=str(Path(__file__).parent / "outputs" / "uploads"),
                )
                if pdf_path:
                    upload_file_path = pdf_path
                    logger.info(f"[API] DocSend PDF saved: {upload_file_path}")
                else:
                    logger.warning(f"[API] DocSend PDF download failed, proceeding with URL scraping")
            except Exception as e:
                logger.warning(f"[API] DocSend PDF download failed: {e}, proceeding with URL scraping")

        # Validate mandate_id
        if not request.mandate_id or not request.mandate_id.strip():
            raise HTTPException(
                status_code=400,
                detail="mandate_id is required. Create a payment mandate before submitting research."
            )

        # Determine engine and model (only OpenAI supported)
        engine = request.engine.lower() if request.engine else "openai"
        if engine != "openai":
            raise HTTPException(status_code=400, detail=f"Invalid engine: {engine}. Only 'openai' is supported.")

        model = request.model or "gpt-5.2-2025-12-11"

        logger.info(f"Creating task for handle: {handle}, engine: {engine}, model: {model}, instant: {request.instant}")
        if request.mandate_id:
            logger.info(f"Payment mandate provided: {request.mandate_id}, budget: ${request.budget_usd}")

        # Create task with payment info and engine
        task = await task_manager.create_task(
            handle=handle,
            version=model,
            engine=engine,
            client_id=client_id,
            mandate_id=request.mandate_id,
            budget_usd=request.budget_usd,
            fluxa_jwt=request.fluxa_jwt or auth_jwt,
            instant=request.instant,
            upload_file=upload_file_path
        )
        logger.info(f"[API] Task created: id={task.task_id}, engine={task.engine}, version={task.version}")

        # Start background task using asyncio.create_task
        # Wrap in try-except to catch immediate failures
        try:
            async_task = asyncio.create_task(run_research_task(task.task_id))
            task_manager.register_running_task(task.task_id, async_task)
            logger.info(f"Background task started: {task.task_id}")
        except Exception as e:
            logger.error(f"Failed to start background task: {e}")
            await task_manager.update_task_status(
                task.task_id, TaskStatus.FAILED, error_message=str(e)
            )

        return TaskResponse(
            task_id=task.task_id,
            handle=task.handle,
            status=task.status.value,
            version=task.version,
            engine=getattr(task, 'engine', 'openai') or 'openai',
            created_at=task.created_at,
            message_count=task.message_count,
            cost_usd=task.cost_usd,
            mandate_id=task.mandate_id,
            budget_usd=task.budget_usd,
            payment_status=task.payment_status.value,
            payment_amount_usd=task.payment_amount_usd,
            tool_calls=task.tool_calls
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating research task: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/research/upload", response_model=TaskResponse, summary="Submit research task with file upload")
async def create_research_with_file(
    http_request: Request,
    handle: str = Form("uploaded_document", description="Research target label"),
    mandate_id: str = Form(..., description="Fluxa mandate ID"),
    budget_usd: float = Form(2.0),
    fluxa_jwt: Optional[str] = Form(None),
    engine: str = Form("openai"),
    model: Optional[str] = Form(None),
    instant: bool = Form(True),
    file: UploadFile = File(..., description="PDF file to research"),
):
    """
    Submit a new research task with an uploaded PDF file.

    The file is saved locally and passed to the research agent as an attachment.
    """
    logger.info(f"[API] POST /research/upload: handle={handle}, file={file.filename}")

    if task_manager is None:
        raise HTTPException(status_code=500, detail="Server not initialized properly")

    try:
        client_id, auth_jwt = require_auth(http_request)

        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        if not mandate_id or not mandate_id.strip():
            raise HTTPException(
                status_code=400,
                detail="mandate_id is required. Create a payment mandate before submitting research."
            )

        # Use filename as display handle if default
        display_handle = handle.strip() or file.filename or "uploaded_document"

        engine_val = engine.lower() if engine else "openai"
        if engine_val != "openai":
            raise HTTPException(status_code=400, detail=f"Invalid engine: {engine_val}. Only 'openai' is supported.")
        model_val = model or "gpt-5.2-2025-12-11"

        # Save uploaded file
        uploads_dir = Path(__file__).parent / "outputs" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        import uuid as _uuid
        safe_filename = f"{_uuid.uuid4().hex[:8]}_{file.filename}"
        upload_path = uploads_dir / safe_filename

        contents = await file.read()
        with open(upload_path, 'wb') as f_out:
            f_out.write(contents)
        logger.info(f"[API] Saved upload: {upload_path} ({len(contents)} bytes)")

        # Create task
        task = await task_manager.create_task(
            handle=display_handle,
            version=model_val,
            engine=engine_val,
            client_id=client_id,
            mandate_id=mandate_id,
            budget_usd=budget_usd,
            fluxa_jwt=fluxa_jwt or auth_jwt,
            instant=instant,
            upload_file=str(upload_path)
        )

        # Start background task
        try:
            async_task = asyncio.create_task(run_research_task(task.task_id))
            task_manager.register_running_task(task.task_id, async_task)
            logger.info(f"Background task started (upload): {task.task_id}")
        except Exception as e:
            logger.error(f"Failed to start background task: {e}")
            await task_manager.update_task_status(
                task.task_id, TaskStatus.FAILED, error_message=str(e)
            )

        return TaskResponse(
            task_id=task.task_id,
            handle=task.handle,
            status=task.status.value,
            version=task.version,
            engine=getattr(task, 'engine', 'openai') or 'openai',
            created_at=task.created_at,
            message_count=task.message_count,
            cost_usd=task.cost_usd,
            mandate_id=task.mandate_id,
            budget_usd=task.budget_usd,
            payment_status=task.payment_status.value,
            payment_amount_usd=task.payment_amount_usd,
            tool_calls=task.tool_calls
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating research task with upload: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/research_lists_magic", response_model=TaskListResponse, summary="List all tasks", include_in_schema=False)
async def list_tasks(
    http_request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """List all research tasks with pagination."""
    client_id = require_client_id(http_request)
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in TaskStatus]}"
            )

    tasks = await task_manager.list_tasks(limit, offset, status_filter, client_id)

    return TaskListResponse(
        tasks=[
            TaskResponse(
                task_id=t.task_id,
                handle=t.handle,
                status=t.status.value,
                version=t.version,
                engine=getattr(t, 'engine', 'openai') or 'openai',
                created_at=t.created_at,
                started_at=t.started_at,
                completed_at=t.completed_at,
                message_count=t.message_count,
                cost_usd=t.cost_usd,
                error_message=t.error_message,
                mandate_id=t.mandate_id,
                budget_usd=t.budget_usd,
                payment_status=t.payment_status.value,
                payment_amount_usd=t.payment_amount_usd,
                tool_calls=t.tool_calls,
                payment_error=t.payment_error,
                payment_tx_hash=t.payment_tx_hash,
                failure_stage=t.failure_stage,
                failure_code=t.failure_code,
                retryable=t.retryable,
                upstream_request_id=t.upstream_request_id
            )
            for t in tasks
        ],
        total=len(tasks)
    )


@app.get("/research/{task_id}", response_model=TaskResponse, summary="Get task status")
async def get_task(task_id: str, http_request: Request):
    """Get task status and details including payment information."""
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    return TaskResponse(
        task_id=task.task_id,
        handle=task.handle,
        status=task.status.value,
        version=task.version,
        engine=getattr(task, 'engine', 'openai') or 'openai',
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        message_count=task.message_count,
        cost_usd=task.cost_usd,
        error_message=task.error_message,
        mandate_id=task.mandate_id,
        budget_usd=task.budget_usd,
        payment_status=task.payment_status.value,
        payment_amount_usd=task.payment_amount_usd,
        tool_calls=task.tool_calls,
        payment_error=task.payment_error,
        payment_tx_hash=task.payment_tx_hash,
        failure_stage=task.failure_stage,
        failure_code=task.failure_code,
        retryable=task.retryable,
        upstream_request_id=task.upstream_request_id
    )


@app.delete("/research/{task_id}", summary="Cancel task")
async def cancel_task(task_id: str, http_request: Request):
    """Cancel a running task."""
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    if task.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not running (status: {task.status.value})"
        )

    cancelled = await task_manager.cancel_task(task_id)
    if cancelled:
        return {"message": f"Task {task_id} cancelled"}
    else:
        raise HTTPException(status_code=500, detail="Failed to cancel task")


@app.get("/research/{task_id}/replay", summary="Stream task log replay")
async def replay_task(
    task_id: str,
    http_request: Request,
    from_line: int = Query(0, ge=0, description="Start from line number"),
    format: str = Query("jsonl", description="Log format: 'jsonl' (structured) or 'text' (legacy)"),
    jwt: Optional[str] = Query(None, description="JWT access token")
):
    """
    Stream the task's message log using Server-Sent Events.

    If the task is running, new lines will be streamed in real-time.
    If completed, the entire log will be replayed.

    Format options:
    - jsonl: Structured JSON objects (recommended for frontend)
    - text: Legacy plain text format
    """
    client_id = require_client_id(http_request, jwt)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    # Prefer JSONL file for structured logs, fallback to text log
    if format == "jsonl" and task.jsonl_file:
        log_path = Path(task.jsonl_file)
        if not log_path.exists() and task.log_file:
            # Fallback to text log if JSONL doesn't exist yet
            log_path = Path(task.log_file)
            format = "text"
    else:
        log_path = Path(task.log_file) if task.log_file else None

    if not log_path or not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    async def event_generator():
        """Generate SSE events from log file.

        Uses binary mode (rb) for reliable seek/tell across reopened
        file handles and adds a final read after the task finishes to
        avoid losing trailing log entries due to a race between the
        task calling unregister_running_task() and the poll loop.
        """
        line_number = 0
        last_position = 0

        def _decode_lines(raw: bytes):
            """Decode bytes to text lines, skipping empty ones."""
            return [
                l for l in raw.decode('utf-8', errors='replace').splitlines()
                if l.strip()
            ]

        # Initial read
        async with aiofiles.open(log_path, 'rb') as f:
            raw = await f.read()
            for line_content in _decode_lines(raw):
                if line_number >= from_line:
                    yield {
                        "event": "log",
                        "data": line_content,
                        "id": str(line_number)
                    }
                line_number += 1
            last_position = await f.tell()

        # Stream new content while task is running
        while task_manager.is_task_running(task_id):
            await asyncio.sleep(0.3)

            async with aiofiles.open(log_path, 'rb') as f:
                await f.seek(last_position)
                new_bytes = await f.read()

                if new_bytes:
                    for line in _decode_lines(new_bytes):
                        yield {
                            "event": "log",
                            "data": line,
                            "id": str(line_number)
                        }
                        line_number += 1

                last_position = await f.tell()

        # Final read: catch any lines written between last poll and
        # the task calling unregister_running_task().
        await asyncio.sleep(0.1)
        async with aiofiles.open(log_path, 'rb') as f:
            await f.seek(last_position)
            remaining = await f.read()
            if remaining:
                for line in _decode_lines(remaining):
                    yield {
                        "event": "log",
                        "data": line,
                        "id": str(line_number)
                    }
                    line_number += 1

        # Send completion event
        updated_task = await task_manager.get_task(task_id)
        yield {
            "event": "complete",
            "data": updated_task.status.value if updated_task else "unknown"
        }

    return EventSourceResponse(event_generator())


@app.get("/research/{task_id}/report", summary="Get or download report")
async def get_report(
    task_id: str,
    http_request: Request,
    download: bool = Query(False, description="Download as file")
):
    """
    Get the research report.

    - Without download param: Returns JSON with report content
    - With download=true: Returns file for download
    """
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Report not available (task status: {task.status.value})"
        )

    # Block report access when payment has failed
    if task.mandate_id and task.payment_status == PaymentStatus.FAILED:
        raise HTTPException(
            status_code=402,
            detail="Payment required - please retry payment before accessing the report"
        )

    report_path = Path(task.report_file) if task.report_file else None
    if not report_path or not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    if download:
        # Return file for download
        return FileResponse(
            path=report_path,
            filename=report_path.name,
            media_type="text/markdown"
        )
    else:
        # Return JSON with content
        async with aiofiles.open(report_path, 'r', encoding='utf-8') as f:
            content = await f.read()

        return ReportResponse(
            task_id=task.task_id,
            handle=task.handle,
            status=task.status.value,
            report={
                "content": content,
                "filename": report_path.name,
                "size_bytes": report_path.stat().st_size
            }
        )


@app.get("/research/{task_id}/log", summary="Download log file")
async def download_log(task_id: str, http_request: Request):
    """Download the task's message log file."""
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    log_path = Path(task.log_file) if task.log_file else None
    if not log_path or not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        path=log_path,
        filename=log_path.name,
        media_type="text/plain"
    )


# ============== Payment API ==============
# Note: Mandate creation is done directly from frontend to Fluxa API

@app.get("/research/{task_id}/payment", response_model=PaymentDetailsResponse, summary="Get payment details")
async def get_payment_details(task_id: str, http_request: Request):
    """
    Get detailed payment information for a task.

    Returns cost breakdown including Claude API costs and tool call costs.
    """
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    # Backfill tool call count from JSONL if missing
    if task.tool_calls == 0 and task.jsonl_file:
        await task_manager.backfill_tool_calls(task)

    # Calculate cost breakdown
    payment_service = get_payment_service()
    cost_breakdown = payment_service.calculate_task_cost(task.cost_usd, task.tool_calls)

    return PaymentDetailsResponse(
        task_id=task.task_id,
        payment_status=task.payment_status.value,
        budget_usd=task.budget_usd,
        claude_cost_usd=cost_breakdown["claude_cost_usd"],
        tool_calls=cost_breakdown["tool_calls"],
        tool_cost_usd=cost_breakdown["tool_cost_usd"],
        total_cost_usd=cost_breakdown["total_cost_usd"],
        payment_amount_usd=task.payment_amount_usd,
        payment_tx_hash=task.payment_tx_hash,
        payment_error=task.payment_error
    )


@app.post("/research/{task_id}/retry-payment", summary="Retry failed payment")
async def retry_payment(task_id: str, http_request: Request, body: RetryPaymentRequest = RetryPaymentRequest()):
    """
    Retry payment for a task whose payment previously failed.

    Only works on completed tasks with payment_status == 'failed'.
    Reuses the existing process_task_payment flow.
    """
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Task is not completed")

    if task.payment_status != PaymentStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Payment is not in failed state (current: {task.payment_status.value})")

    # Use new mandate if provided, otherwise fall back to stored mandate
    mandate_id = body.mandate_id or task.mandate_id
    if not mandate_id:
        raise HTTPException(status_code=400, detail="No mandate associated with this task")

    # Use fresh JWT from request body, or fall back to stored JWT
    fluxa_jwt = body.fluxa_jwt or task.fluxa_jwt

    # If a new mandate was provided, update the task record
    if body.mandate_id and body.mandate_id != task.mandate_id:
        await task_manager.update_task_mandate(task_id, body.mandate_id, fluxa_jwt)

    try:
        await process_task_payment(
            task_id=task.task_id,
            mandate_id=mandate_id,
            fluxa_jwt=fluxa_jwt,
            claude_cost_usd=task.cost_usd,
            tool_calls=task.tool_calls
        )

        # Fetch updated task to return current payment status
        updated_task = await task_manager.get_task(task_id)
        return {
            "success": updated_task.payment_status == PaymentStatus.COMPLETED,
            "payment_status": updated_task.payment_status.value,
            "payment_amount_usd": updated_task.payment_amount_usd,
            "payment_tx_hash": updated_task.payment_tx_hash,
            "payment_error": updated_task.payment_error,
        }
    except Exception as e:
        logger.error(f"Retry payment failed for task {task_id}: {e}")
        return {
            "success": False,
            "payment_status": "failed",
            "error": str(e),
        }


@app.post("/research/{task_id}/retry", summary="Retry failed research task")
async def retry_research(task_id: str, http_request: Request):
    """
    Retry a research task that previously failed.

    Resets the task to pending and re-launches the research agent
    with the same handle, mandate, and configuration.
    Only works on tasks with status 'failed'.
    """
    client_id = require_client_id(http_request)
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    ensure_task_owner(task, client_id)

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Only failed tasks can be retried (current: {task.status.value})")

    if task_manager.is_task_running(task_id):
        raise HTTPException(status_code=409, detail="Task is already running")

    # Reset task status to pending and clear error fields
    await task_manager.update_task_status(
        task_id, TaskStatus.PENDING,
        error_message=None,
        failure_stage=None,
        failure_code=None,
        retryable=None,
        upstream_request_id=None
    )

    # Re-launch the background research task
    async_task = asyncio.create_task(run_research_task(task_id))
    task_manager.register_running_task(task_id, async_task)
    logger.info(f"[API] Research retry started for task: {task_id}")

    updated_task = await task_manager.get_task(task_id)
    return TaskResponse(
        task_id=updated_task.task_id,
        handle=updated_task.handle,
        status=updated_task.status.value,
        version=updated_task.version,
        engine=getattr(updated_task, 'engine', 'openai') or 'openai',
        created_at=updated_task.created_at,
        started_at=updated_task.started_at,
        mandate_id=updated_task.mandate_id,
        budget_usd=updated_task.budget_usd,
        payment_status=updated_task.payment_status.value,
    )


# ============== Tools API ==============

def get_firecrawl_api() -> FirecrawlAPI:
    """Get or create FirecrawlAPI instance (lazy loading)."""
    global firecrawl_api
    if firecrawl_api is None:
        firecrawl_api = FirecrawlAPI()
    return firecrawl_api


@app.post("/tools/webfetch_magic", response_model=WebFetchResponse, summary="Fetch web content", include_in_schema=False)
async def webfetch(request: WebFetchRequest):
    """
    Fetch and extract content from a URL using Firecrawl.

    Returns markdown content (truncated to max_length) and discovered links.
    """
    try:
        api = get_firecrawl_api()
        result = api.scrape_website(request.url, request.max_length)

        return WebFetchResponse(
            url=result.get("url", request.url),
            content=result.get("content"),
            original_length=result.get("original_length"),
            truncated_length=result.get("truncated_length"),
            links=result.get("links"),
            error=result.get("error")
        )
    except ValueError as e:
        # API key not set
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"WebFetch error: {e}")
        return WebFetchResponse(
            url=request.url,
            error=str(e)
        )




def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Research Agent Web Server")
    parser.add_argument(
        "--version", "-v",
        type=str,
        default="v3",
        choices=["v1", "v3"],
        help="Agent version to use (default: v3)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="claude-opus-4-5-20251101",
        help="Model to use (default: claude-opus-4-5-20251101)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="Port to run server on (default: 8000, or PORT env var)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    # Update global config
    config.version = args.version
    config.model = args.model
    config.port = args.port

    # Run server
    import uvicorn
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
