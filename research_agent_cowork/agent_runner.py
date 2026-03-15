#!/usr/bin/env python3
"""
Agent Runner for Research Agent Web Server.

Provides unified interface for running v1 and v3 agents.
"""

import os
import sys
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from dotenv import load_dotenv
load_dotenv('../.env')
load_dotenv()

logger = logging.getLogger(__name__)

# Import Claude Agent SDK
try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        UserMessage,
    )
    from claude_agent_sdk.types import TextBlock, ToolUseBlock, ToolResultBlock
except ImportError:
    logger.error("Claude Agent SDK not installed. Run: pip install claude-agent-sdk")
    sys.exit(1)

# Import structured logger
from structured_logger import StructuredLogger


class AgentResult:
    """Result from agent execution."""

    def __init__(
        self,
        success: bool,
        report: Optional[str] = None,
        report_file: Optional[str] = None,
        log_file: Optional[str] = None,
        jsonl_file: Optional[str] = None,
        message_count: int = 0,
        tool_call_count: int = 0,
        cost_usd: float = 0.0,
        duration_seconds: float = 0.0,
        error: Optional[str] = None
    ):
        self.success = success
        self.report = report
        self.report_file = report_file
        self.log_file = log_file
        self.jsonl_file = jsonl_file  # Structured JSONL log for frontend
        self.message_count = message_count
        self.tool_call_count = tool_call_count
        self.cost_usd = cost_usd
        self.duration_seconds = duration_seconds
        self.error = error


# Progress callback type: (message_count, cost_usd, tool_call_count)
ProgressCallback = Callable[[int, float, int], Awaitable[None]]


class BaseAgentRunner(ABC):
    """Base class for agent runners."""

    def __init__(self, model: str = "claude-opus-4-5-20251101"):
        self.model = model
        self.base_dir = Path(__file__).parent

        # MCP server paths
        self.twitter_mcp_path = self.base_dir / "twitter_mcp.py"
        self.firecrawl_mcp_path = self.base_dir / "firecrawl_mcp.py"

    @abstractmethod
    async def run(
        self,
        handle: str,
        output_dir: Path,
        log_file: Path,
        report_file: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> AgentResult:
        """Run the research agent."""
        pass

    def _get_mcp_servers(self) -> dict:
        """Get MCP server configuration."""
        return {
            "twitter": {
                "command": "python",
                "args": [str(self.twitter_mcp_path)]
            },
            "firecrawl": {
                "command": "python",
                "args": [str(self.firecrawl_mcp_path)]
            }
        }


class AgentRunnerV1(BaseAgentRunner):
    """V1 Agent Runner - Full system prompt mode."""

    def _load_prompt(self) -> str:
        """Load the VC research prompt."""
        prompt_path = self.base_dir.parent / "research_agent" / "research_agent_prompt_al.md"
        if prompt_path.exists():
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    async def run(
        self,
        handle: str,
        output_dir: Path,
        log_file: Path,
        report_file: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> AgentResult:
        """Run V1 agent with full system prompt."""
        clean_handle = handle.replace('@', '')
        start_time = datetime.now()

        # Setup dual-file logging: .log (human) + .jsonl (frontend)
        jsonl_file = log_file.with_suffix('.jsonl')
        slog = StructuredLogger(
            log_file=log_file,
            jsonl_file=jsonl_file,
            target=f"@{clean_handle}",
            version="V1",
            model=self.model
        )

        try:
            system_prompt = self._load_prompt()
            user_prompt = f"Research the Twitter profile @{clean_handle}."

            report_content = []
            message_count = 0
            tool_call_count = 0
            sdk_final_cost = 0.0

            # Open dual log files
            slog.open()
            slog.log_app(f"Starting V1 research for @{clean_handle}", level="info")

            options = ClaudeAgentOptions(
                allowed_tools=["WebSearch", "WebFetch", "Write", "Read"],
                permission_mode="bypassPermissions",
                mcp_servers=self._get_mcp_servers(),
                system_prompt=system_prompt,
                cwd=str(output_dir),
                model=self.model,
                setting_sources=["user", "project"],
            )

            slog.log_app(f"Agent options configured, starting query", level="debug")

            async for message in query(prompt=user_prompt, options=options):
                message_count += 1

                # Log message to both files
                slog.log_message(message)

                # Count actual tool calls
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_call_count += 1

                # Extract result
                if isinstance(message, ResultMessage):
                    if message.total_cost_usd:
                        sdk_final_cost = message.total_cost_usd
                    if message.result:
                        report_content.append(message.result)

                # Progress callback
                if progress_callback:
                    await progress_callback(message_count, sdk_final_cost, tool_call_count)

            elapsed = (datetime.now() - start_time).total_seconds()

            # Close logs with summary
            slog.log_app(f"Research completed successfully", level="info")
            slog.close(
                duration=elapsed,
                message_count=message_count,
                cost_usd=sdk_final_cost,
                success=True
            )

            # Compile report
            report = "\n".join(filter(None, report_content))
            report_with_meta = self._add_metadata(
                report, clean_handle, elapsed, message_count, sdk_final_cost, "V1"
            )

            # Save report
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_with_meta)

            return AgentResult(
                success=True,
                report=report_with_meta,
                report_file=str(report_file),
                log_file=str(log_file),
                jsonl_file=str(jsonl_file),
                message_count=message_count,
                tool_call_count=tool_call_count,
                cost_usd=sdk_final_cost,
                duration_seconds=elapsed
            )

        except Exception as e:
            logger.error(f"V1 Agent failed: {e}")
            elapsed = (datetime.now() - start_time).total_seconds()
            try:
                slog.log_error(str(e))
                slog.close(
                    duration=elapsed,
                    message_count=message_count if 'message_count' in dir() else 0,
                    cost_usd=sdk_final_cost if 'sdk_final_cost' in dir() else 0.0,
                    success=False,
                    error=str(e)
                )
            except:
                pass
            return AgentResult(
                success=False,
                error=str(e),
                log_file=str(log_file),
                jsonl_file=str(jsonl_file),
                duration_seconds=elapsed
            )

    def _log_message(self, log_file, message, count: int, ts: str):
        """Log a message to the log file."""
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    log_file.write(f"[{ts}] [{count}] ASSISTANT TEXT:\n{block.text}\n{'-'*40}\n\n")
                elif isinstance(block, ToolUseBlock):
                    tool_input = block.input if hasattr(block, 'input') else {}
                    input_str = json.dumps(tool_input, indent=2, ensure_ascii=False) if isinstance(tool_input, dict) else str(tool_input)
                    log_file.write(f"[{ts}] [{count}] TOOL CALL: {block.name}\nInput:\n{input_str}\n{'-'*40}\n\n")
        elif isinstance(message, ResultMessage):
            log_file.write(f"[{ts}] [{count}] RESULT: {message.subtype}\n")
            log_file.write(f"Duration: {message.duration_ms}ms | Turns: {message.num_turns} | Cost: ${message.total_cost_usd or 0:.4f}\n")
            if message.result:
                log_file.write(f"Result:\n{message.result}\n")
            log_file.write(f"{'='*40}\n\n")
        elif isinstance(message, SystemMessage):
            data_str = json.dumps(message.data, indent=2, ensure_ascii=False) if isinstance(message.data, dict) else str(message.data)
            log_file.write(f"[{ts}] [{count}] SYSTEM: {message.subtype}\nData:\n{data_str}\n{'-'*40}\n\n")
        elif isinstance(message, UserMessage):
            if hasattr(message, 'content') and message.content:
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        tool_id = getattr(block, 'tool_use_id', 'unknown')[:12]
                        content = str(block.content) if hasattr(block, 'content') else str(block)
                        log_file.write(f"[{ts}] [{count}] TOOL RESULT: {tool_id}...\nOutput:\n{content}\n{'-'*40}\n\n")

    def _add_metadata(self, report: str, handle: str, duration: float, messages: int, cost: float, version: str) -> str:
        """Add metadata header to report."""
        return f"""# Research Report: @{handle}
Generated: {datetime.now().isoformat()}
Method: Claude Agent SDK ({version})
Model: {self.model}
Duration: {duration:.1f}s
Messages: {messages}
Total Cost: ${cost:.4f}

---

{report}
"""


class AgentRunnerV3(BaseAgentRunner):
    """V3 Agent Runner - Skill-based mode."""

    async def run(
        self,
        handle: str,
        output_dir: Path,
        log_file: Path,
        report_file: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> AgentResult:
        """Run V3 agent with skill."""
        clean_handle = handle.replace('@', '')
        start_time = datetime.now()

        # Verify skill exists
        skill_dir = self.base_dir / ".claude" / "skills" / "vc-research"
        if not skill_dir.exists():
            return AgentResult(
                success=False,
                error=f"Skill directory not found: {skill_dir}"
            )

        # Setup dual-file logging: .log (human) + .jsonl (frontend)
        jsonl_file = log_file.with_suffix('.jsonl')
        slog = StructuredLogger(
            log_file=log_file,
            jsonl_file=jsonl_file,
            target=f"@{clean_handle}",
            version="V3",
            model=self.model,
            extra_meta={"skill": "vc-research"}
        )

        try:
            user_prompt = f"""Use the vc-research skill to research @{clean_handle}. Write the report to {report_file}."""

            report_content = []
            message_count = 0
            tool_call_count = 0
            sdk_final_cost = 0.0

            # Open dual log files
            slog.open()
            slog.log_app(f"Starting V3 skill-based research for @{clean_handle}", level="info")

            options = ClaudeAgentOptions(
                allowed_tools=["Skill", "Read", "WebSearch", "WebFetch", "Write"],
                permission_mode="bypassPermissions",
                mcp_servers=self._get_mcp_servers(),
                cwd=str(self.base_dir),
                model=self.model,
                setting_sources=["user", "project"],
            )

            slog.log_app(f"Agent options configured with skill mode", level="debug")

            async for message in query(prompt=user_prompt, options=options):
                message_count += 1

                # Log message to both files
                slog.log_message(message)

                # Count actual tool calls
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_call_count += 1

                # Extract result
                if isinstance(message, ResultMessage):
                    if message.total_cost_usd:
                        sdk_final_cost = message.total_cost_usd
                    if message.result:
                        report_content.append(message.result)

                # Progress callback
                if progress_callback:
                    await progress_callback(message_count, sdk_final_cost, tool_call_count)

            elapsed = (datetime.now() - start_time).total_seconds()

            # Compile report
            report = "\n".join(filter(None, report_content))

            # Check if report file was written by agent
            if report_file.exists():
                with open(report_file, 'r', encoding='utf-8') as f:
                    report = f.read()
                slog.log_app(f"Report file written by agent: {report_file}", level="info")
            elif report:
                # Agent returned report but didn't write file
                report_with_meta = self._add_metadata(
                    report, clean_handle, elapsed, message_count, sdk_final_cost, "V3 Skill"
                )
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(report_with_meta)
                report = report_with_meta
                slog.log_app(f"Report compiled from result messages", level="info")

            # Close logs with summary
            slog.log_app(f"V3 research completed successfully", level="info")
            slog.close(
                duration=elapsed,
                message_count=message_count,
                cost_usd=sdk_final_cost,
                success=True
            )

            return AgentResult(
                success=True,
                report=report,
                report_file=str(report_file),
                log_file=str(log_file),
                jsonl_file=str(jsonl_file),
                message_count=message_count,
                tool_call_count=tool_call_count,
                cost_usd=sdk_final_cost,
                duration_seconds=elapsed
            )

        except Exception as e:
            logger.error(f"V3 Agent failed: {e}")
            elapsed = (datetime.now() - start_time).total_seconds()
            try:
                slog.log_error(str(e))
                slog.close(
                    duration=elapsed,
                    message_count=message_count if 'message_count' in dir() else 0,
                    cost_usd=sdk_final_cost if 'sdk_final_cost' in dir() else 0.0,
                    success=False,
                    error=str(e)
                )
            except:
                pass
            return AgentResult(
                success=False,
                error=str(e),
                log_file=str(log_file),
                jsonl_file=str(jsonl_file),
                duration_seconds=elapsed
            )

    def _add_metadata(self, report: str, handle: str, duration: float, messages: int, cost: float, version: str) -> str:
        """Add metadata header to report."""
        return AgentRunnerV1._add_metadata(self, report, handle, duration, messages, cost, version)


class AgentRunnerOpenAI(BaseAgentRunner):
    """OpenAI Reasoning Model Runner (gpt-5.2, o3, etc.)

    Uses research_agent/streaming_processor.py to call OpenAI Responses API
    with MCP tools. Produces JSONL logs compatible with the frontend.
    """

    def __init__(self, model: str = "gpt-5.2-2025-12-11", use_flex: bool = True):
        super().__init__(model=model)
        self.use_flex = use_flex

    def _load_prompt(self) -> str:
        """Load the VC research prompt."""
        prompt_path = self.base_dir.parent / "research_agent" / "research_agent_prompt_al.md"
        if prompt_path.exists():
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    @staticmethod
    def _extract_name_from_url(url: str) -> str:
        """Extract a filesystem-safe short name from a URL."""
        from urllib.parse import urlparse
        import re as _re
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '').split('.')[0]
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        name = path_parts[-1][:30] if path_parts else domain
        return _re.sub(r'[^\w-]', '_', name)[:40] or 'research'

    async def run(
        self,
        handle: str,
        output_dir: Path,
        log_file: Path,
        report_file: Path,
        progress_callback: Optional[ProgressCallback] = None,
        upload_file: Optional[str] = None
    ) -> AgentResult:
        """Run OpenAI research agent."""
        is_url = handle.startswith('http://') or handle.startswith('https://')
        if is_url:
            clean_handle = self._extract_name_from_url(handle)
        else:
            clean_handle = handle.replace('@', '')
        start_time = datetime.now()

        # Setup JSONL log for frontend (compatible with StructuredLogger format)
        jsonl_file = log_file.with_suffix('.jsonl')
        seq = 0
        jsonl_handle = None

        def _next_seq():
            nonlocal seq
            seq += 1
            return seq

        def _get_ts():
            return datetime.now().strftime("%H:%M:%S")

        def _write_jsonl(entry: dict):
            if jsonl_handle and not jsonl_handle.closed:
                jsonl_handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                jsonl_handle.flush()

        def _write_log(text: str):
            if log_handle and not log_handle.closed:
                log_handle.write(text + "\n")
                log_handle.flush()

        # Event callback for streaming chunks → JSONL
        chunk_count = 0
        tool_call_count = 0
        _text_buffer = []       # Accumulate text deltas → flush as one JSONL entry
        _thinking_buffer = []   # Accumulate thinking deltas → flush as one JSONL entry

        def _flush_text_buffer():
            """Flush accumulated text deltas as a single assistant_text JSONL entry."""
            if _text_buffer:
                combined = ''.join(_text_buffer)
                _text_buffer.clear()
                if combined.strip():
                    ts = _get_ts()
                    _write_jsonl({
                        "type": "assistant_text",
                        "ts": ts,
                        "seq": _next_seq(),
                        "model": self.model,
                        "content": combined,
                        "redacted": False
                    })
                    _write_log(f"[{ts}] [{seq}] ASSISTANT TEXT: {combined[:200]}...")

        def _flush_thinking_buffer():
            """Flush accumulated thinking deltas as a single assistant_thinking JSONL entry."""
            if _thinking_buffer:
                combined = ''.join(_thinking_buffer)
                _thinking_buffer.clear()
                if combined.strip():
                    ts = _get_ts()
                    _write_jsonl({
                        "type": "assistant_thinking",
                        "ts": ts,
                        "seq": _next_seq(),
                        "model": self.model,
                        "content": combined,
                        "redacted": False
                    })

        def on_event(chunk):
            """Convert OpenAI streaming chunk to frontend JSONL format."""
            nonlocal chunk_count, tool_call_count
            chunk_count += 1
            ts = _get_ts()

            try:
                # Extract event type
                event_type = getattr(chunk, 'type', 'unknown')

                # --- Text deltas: buffer instead of writing immediately ---
                # OpenAI SDK uses chunk.text or chunk.delta depending on version
                if event_type == 'response.output_text.delta':
                    text = getattr(chunk, 'text', '') or getattr(chunk, 'delta', '')
                    if text:
                        _text_buffer.append(text)

                elif event_type in (
                    'response.reasoning_summary_text.delta',
                    'response.reasoning_text.delta',
                    'response.reasoning_summary.delta',
                ):
                    # Buffer thinking deltas to avoid word-by-word UI
                    text = getattr(chunk, 'text', '') or getattr(chunk, 'delta', '')
                    if text:
                        _thinking_buffer.append(text)

                # --- Boundary events: flush text buffer ---
                elif event_type in ('response.output_text.done', 'response.content_part.done'):
                    _flush_text_buffer()
                elif event_type in ('response.reasoning_summary_part.done', 'response.completed'):
                    _flush_thinking_buffer()

                # --- output_item.done: flush + detect MCP tool calls ---
                # This is where OpenAI delivers complete MCP call data
                # (matching streaming_logger.py:246-270 pattern)
                elif event_type == 'response.output_item.done':
                    _flush_text_buffer()

                    if hasattr(chunk, 'item') and chunk.item:
                        item = chunk.item
                        item_type = getattr(item, 'type', '')
                        if item_type == 'mcp_call':
                            tool_call_count += 1
                            tool_name = getattr(item, 'name', 'unknown')
                            tool_input = {}
                            raw_args = getattr(item, 'arguments', '')
                            if raw_args:
                                try:
                                    tool_input = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                except:
                                    tool_input = {"raw": str(raw_args)[:500]}
                            _write_jsonl({
                                "type": "tool_call",
                                "ts": ts,
                                "seq": _next_seq(),
                                "model": self.model,
                                "tool": tool_name,
                                "tool_use_id": getattr(item, 'call_id', getattr(item, 'id', '')),
                                "input": tool_input,
                                "redacted": False
                            })
                            # Log tool result if available on the same item
                            output = getattr(item, 'output', '')
                            if output:
                                _write_jsonl({
                                    "type": "tool_result",
                                    "ts": ts,
                                    "seq": _next_seq(),
                                    "tool_use_id": getattr(item, 'call_id', getattr(item, 'id', '')),
                                    "output": str(output)[:2000],
                                    "is_error": False,
                                    "redacted": False
                                })
                            _write_log(f"[{ts}] [{seq}] TOOL CALL: {tool_name}")

                # --- Fallback MCP handlers (kept for forward-compat) ---
                elif event_type == 'response.mcp_call':
                    tool_call_count += 1
                    _flush_text_buffer()

                    tool_name = ''
                    tool_input = {}
                    if hasattr(chunk, 'name'):
                        tool_name = chunk.name
                    elif hasattr(chunk, 'item') and hasattr(chunk.item, 'name'):
                        tool_name = chunk.item.name
                    if hasattr(chunk, 'arguments'):
                        try:
                            tool_input = json.loads(chunk.arguments) if isinstance(chunk.arguments, str) else chunk.arguments
                        except:
                            tool_input = {"raw": str(chunk.arguments)[:500]}
                    _write_jsonl({
                        "type": "tool_call",
                        "ts": ts,
                        "seq": _next_seq(),
                        "model": self.model,
                        "tool": tool_name,
                        "tool_use_id": getattr(chunk, 'call_id', ''),
                        "input": tool_input,
                        "redacted": False
                    })
                    _write_log(f"[{ts}] [{seq}] TOOL CALL: {tool_name}")

                elif event_type == 'response.mcp_call.completed':
                    _flush_text_buffer()

                    tool_name = ''
                    if hasattr(chunk, 'name'):
                        tool_name = chunk.name
                    elif hasattr(chunk, 'item') and hasattr(chunk.item, 'name'):
                        tool_name = chunk.item.name
                    _write_log(f"[{ts}] TOOL COMPLETED: {tool_name}")

                elif event_type in ('response.web_search_call', 'response.web_search_call.in_progress'):
                    tool_call_count += 1
                    _flush_text_buffer()

                    # Extract query from multiple possible fields/encodings
                    query = getattr(chunk, 'query', None)
                    if not query:
                        raw_args = None
                        if hasattr(chunk, 'arguments'):
                            raw_args = chunk.arguments
                        elif hasattr(chunk, 'item') and hasattr(chunk.item, 'arguments'):
                            raw_args = chunk.item.arguments
                        if raw_args:
                            try:
                                args_obj = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                if isinstance(args_obj, dict):
                                    query = args_obj.get('query') or args_obj.get('search_query') or ''
                            except Exception:
                                query = ''
                    if not query and hasattr(chunk, 'item') and hasattr(chunk.item, 'query'):
                        query = chunk.item.query
                    if not query:
                        query = ''

                    _write_jsonl({
                        "type": "tool_call",
                        "ts": ts,
                        "seq": _next_seq(),
                        "model": self.model,
                        "tool": "web_search",
                        "tool_use_id": getattr(chunk, 'id', ''),
                        "input": {"query": query},
                        "redacted": False
                    })
                    _write_log(f"[{ts}] [{seq}] WEB SEARCH: {query}")

                elif event_type == 'response.completed':
                    _flush_text_buffer()

                    _write_jsonl({
                        "type": "app",
                        "ts": ts,
                        "seq": _next_seq(),
                        "level": "info",
                        "message": "OpenAI response completed"
                    })

            except Exception as e:
                logger.debug(f"Event callback error (non-critical): {e}")

        log_handle = None
        try:
            # Open log files
            jsonl_handle = open(jsonl_file, 'w', encoding='utf-8')
            log_handle = open(log_file, 'w', encoding='utf-8')

            # Write session start
            _write_jsonl({
                "type": "session_start",
                "ts": _get_ts(),
                "seq": _next_seq(),
                "target": f"@{clean_handle}",
                "version": "OpenAI",
                "model": self.model,
                "started_at": start_time.isoformat()
            })
            _write_log(f"{'='*80}")
            _write_log(f"Research Agent OpenAI Message Log")
            _write_log(f"Target: @{clean_handle}")
            _write_log(f"Started: {start_time.isoformat()}")
            _write_log(f"Model: {self.model}")
            _write_log(f"{'='*80}\n")

            _write_jsonl({
                "type": "app",
                "ts": _get_ts(),
                "seq": _next_seq(),
                "level": "info",
                "message": f"Starting OpenAI research for @{clean_handle} with model {self.model}"
            })

            # Load prompt and prepare query based on input type
            system_prompt = self._load_prompt()
            if upload_file and Path(upload_file).exists():
                user_query = f"Research the uploaded document. The file is attached as a PDF."
            elif is_url:
                user_query = f"Research the following URL: {handle}"
            else:
                user_query = f"Research the Twitter profile @{clean_handle}."

            # Read uploaded file for base64 encoding
            file_base64 = None
            if upload_file and Path(upload_file).exists():
                import base64 as b64
                with open(upload_file, 'rb') as uf:
                    file_base64 = b64.b64encode(uf.read()).decode('utf-8')
                logger.info(f"[BG] Loaded upload file: {upload_file} ({len(file_base64)} bytes base64)")

            # Get MCP server URL (public URL for OpenAI to connect back)
            mcp_url = os.environ.get(
                "OPENAI_MCP_SERVER_URL",
                "https://web-production-1b829.up.railway.app/mcp/sse"
            )


            # Import StreamingProcessor (from research_agent/)
            sys.path.insert(0, str(self.base_dir.parent / "research_agent"))
            from streaming_processor import StreamingProcessor

            # Create processor
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")

            processor = StreamingProcessor(
                api_key=api_key,
                model=self.model,
                use_flex=self.use_flex,
                session_dir=str(output_dir),
                twitter_handle=clean_handle,
                project_name=clean_handle,
            )

            # Run synchronous processor in thread to avoid blocking event loop
            final_output = await asyncio.to_thread(
                processor.process_research,
                system_prompt,
                user_query,
                mcp_url,
                max_retries=3,
                event_callback=on_event,
                file_base64=file_base64
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            # Parse cost from metrics file if available
            cost_usd = 0.0
            metrics_file = output_dir / clean_handle / "04_metrics.json"
            if metrics_file.exists():
                try:
                    with open(metrics_file, 'r') as f:
                        metrics = json.load(f)
                    tokens = metrics.get('tokens', {})
                    # GPT-5.2 pricing estimate
                    input_cost = (tokens.get("input", 0) - tokens.get("cached_input", 0)) * 1.25 / 1_000_000
                    cached_cost = tokens.get("cached_input", 0) * 0.125 / 1_000_000
                    output_cost = tokens.get("output", 0) * 10.0 / 1_000_000
                    cost_usd = input_cost + cached_cost + output_cost
                except Exception as e:
                    logger.warning(f"Failed to parse metrics: {e}")

            if final_output:
                # Write report
                report_with_meta = self._add_metadata(
                    final_output, clean_handle, elapsed, chunk_count, cost_usd, f"OpenAI {self.model}"
                )
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(report_with_meta)

                # Write session end
                _write_jsonl({
                    "type": "session_end",
                    "ts": _get_ts(),
                    "seq": _next_seq(),
                    "success": True,
                    "duration_seconds": elapsed,
                    "message_count": chunk_count,
                    "cost_usd": cost_usd,
                    "error": None
                })

                # Progress callback
                if progress_callback:
                    await progress_callback(chunk_count, cost_usd, tool_call_count)

                return AgentResult(
                    success=True,
                    report=report_with_meta,
                    report_file=str(report_file),
                    log_file=str(log_file),
                    jsonl_file=str(jsonl_file),
                    message_count=chunk_count,
                    tool_call_count=tool_call_count,
                    cost_usd=cost_usd,
                    duration_seconds=elapsed
                )
            else:
                # No output
                _write_jsonl({
                    "type": "error",
                    "ts": _get_ts(),
                    "seq": _next_seq(),
                    "message": "No output returned from OpenAI",
                    "detail": {"provider": "openai", "model": self.model, "endpoint": "responses"}
                })
                _write_log(f"[{_get_ts()}] ERROR: No output returned from OpenAI (model={self.model})")
                _write_jsonl({
                    "type": "session_end",
                    "ts": _get_ts(),
                    "seq": _next_seq(),
                    "success": False,
                    "duration_seconds": elapsed,
                    "message_count": chunk_count,
                    "cost_usd": cost_usd,
                    "error": "No output returned from OpenAI",
                    "error_detail": {"provider": "openai", "model": self.model}
                })
                return AgentResult(
                    success=False,
                    error="No output returned from OpenAI",
                    log_file=str(log_file),
                    jsonl_file=str(jsonl_file),
                    duration_seconds=elapsed
                )

        except Exception as e:
            logger.error(f"OpenAI Agent failed: {e}")
            import traceback
            traceback.print_exc()
            elapsed = (datetime.now() - start_time).total_seconds()

            # Extract structured error details from OpenAI exceptions
            error_detail = {
                "provider": "openai",
                "model": self.model,
                "endpoint": "responses",
                "error_type": type(e).__name__,
                "error_message": str(e),
            }
            # OpenAI SDK exceptions may carry status_code and request_id
            if hasattr(e, 'status_code'):
                error_detail["upstream_status_code"] = e.status_code
            if hasattr(e, 'request_id'):
                error_detail["upstream_request_id"] = e.request_id
            elif hasattr(e, 'response') and hasattr(e.response, 'headers'):
                error_detail["upstream_request_id"] = e.response.headers.get('x-request-id')
            # Also try to extract req_xxx from error string
            import re as _re
            req_match = _re.search(r'(req_[a-zA-Z0-9]+)', str(e))
            if req_match and "upstream_request_id" not in error_detail:
                error_detail["upstream_request_id"] = req_match.group(1)

            try:
                _write_jsonl({
                    "type": "error",
                    "ts": _get_ts(),
                    "seq": _next_seq(),
                    "message": str(e),
                    "detail": error_detail
                })
                _write_log(f"[{_get_ts()}] ERROR: {str(e)}")
                _write_log(f"  provider=openai model={self.model} error_type={type(e).__name__}")
                if error_detail.get("upstream_status_code"):
                    _write_log(f"  upstream_status_code={error_detail['upstream_status_code']}")
                if error_detail.get("upstream_request_id"):
                    _write_log(f"  upstream_request_id={error_detail['upstream_request_id']}")
                _write_jsonl({
                    "type": "session_end",
                    "ts": _get_ts(),
                    "seq": _next_seq(),
                    "success": False,
                    "duration_seconds": elapsed,
                    "message_count": chunk_count,
                    "cost_usd": 0.0,
                    "error": str(e),
                    "error_detail": error_detail
                })
            except:
                pass
            return AgentResult(
                success=False,
                error=str(e),
                log_file=str(log_file),
                jsonl_file=str(jsonl_file),
                duration_seconds=elapsed
            )
        finally:
            try:
                # Flush any remaining buffered text before closing
                _flush_text_buffer()
            except:
                pass
            try:
                if jsonl_handle and not jsonl_handle.closed:
                    jsonl_handle.close()
                if log_handle and not log_handle.closed:
                    log_handle.close()
            except:
                pass

    def _add_metadata(self, report: str, handle: str, duration: float, messages: int, cost: float, version: str) -> str:
        """Add metadata header to report."""
        return f"""# Research Report: @{handle}
Generated: {datetime.now().isoformat()}
Method: OpenAI Responses API ({version})
Model: {self.model}
Duration: {duration:.1f}s
Messages: {messages}
Total Cost: ${cost:.4f}

---

{report}
"""


def get_agent_runner(version: str, model: str = "claude-opus-4-5-20251101") -> BaseAgentRunner:
    """Factory function to get the appropriate agent runner."""
    if version == "v1":
        return AgentRunnerV1(model=model)
    elif version == "v3":
        return AgentRunnerV3(model=model)
    else:
        raise ValueError(f"Unknown version: {version}. Must be v1 or v3.")
