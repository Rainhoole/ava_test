#!/usr/bin/env python3
"""
Structured Logger for Agent SDK Messages.

Outputs JSONL format for frontend consumption alongside human-readable logs.
Handles all Message Types and ContentBlock Types from Claude Agent SDK.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TextIO

# Import Claude Agent SDK types
try:
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        UserMessage,
    )
    from claude_agent_sdk.types import (
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
        ThinkingBlock,
    )
except ImportError:
    # Fallback for type hints
    AssistantMessage = Any
    ResultMessage = Any
    SystemMessage = Any
    UserMessage = Any
    TextBlock = Any
    ToolUseBlock = Any
    ToolResultBlock = Any
    ThinkingBlock = Any


class StructuredLogger:
    """
    Dual-file logger: .log (human-readable) + .jsonl (frontend).

    Log entry types:
    - app: Application/program logs
    - user_message: UserMessage
    - assistant_text: AssistantMessage with TextBlock
    - assistant_thinking: AssistantMessage with ThinkingBlock
    - tool_call: AssistantMessage with ToolUseBlock
    - tool_result: UserMessage with ToolResultBlock
    - system: SystemMessage
    - result: ResultMessage
    - stream_event: StreamEvent (if enabled)
    - error: Error messages
    - session_start: Session metadata
    - session_end: Session completion summary
    """

    # Sensitive prompt patterns for redaction (class-level constant)
    SENSITIVE_PROMPT_PATTERNS = [
        "# Pre-Seed/Seed VC Research Skill",           # V3 skill
        "# Pre-Seed/Seed VC Research Agent System Prompt",  # V1 system prompt
        "## Asymmetric Success Pattern Recognition Framework",  # Both V1 and V3
    ]

    def __init__(
        self,
        log_file: Path,
        jsonl_file: Path,
        target: str,
        version: str,
        model: str,
        extra_meta: Optional[dict] = None
    ):
        """
        Initialize dual-file logger.

        Args:
            log_file: Path to human-readable .log file
            jsonl_file: Path to structured .jsonl file
            target: Research target (e.g., "@username")
            version: Agent version (e.g., "V1", "V3")
            model: Model name
            extra_meta: Additional metadata for session_start
        """
        self.log_file = log_file
        self.jsonl_file = jsonl_file
        self.target = target
        self.version = version
        self.model = model
        self.extra_meta = extra_meta or {}

        self._log_handle: Optional[TextIO] = None
        self._jsonl_handle: Optional[TextIO] = None
        self._seq = 0
        self._start_time = datetime.now()

    def open(self):
        """Open both log files and write session start."""
        self._log_handle = open(self.log_file, 'w', encoding='utf-8')
        self._jsonl_handle = open(self.jsonl_file, 'w', encoding='utf-8')

        # Write human-readable header
        self._log_handle.write(f"{'='*80}\n")
        self._log_handle.write(f"Research Agent {self.version} Message Log\n")
        self._log_handle.write(f"Target: {self.target}\n")
        self._log_handle.write(f"Started: {self._start_time.isoformat()}\n")
        self._log_handle.write(f"Model: {self.model}\n")
        if self.extra_meta:
            for k, v in self.extra_meta.items():
                self._log_handle.write(f"{k}: {v}\n")
        self._log_handle.write(f"{'='*80}\n\n")

        # Write JSONL session_start
        self._write_jsonl({
            "type": "session_start",
            "ts": self._get_ts(),
            "seq": self._next_seq(),
            "target": self.target,
            "version": self.version,
            "model": self.model,
            "started_at": self._start_time.isoformat(),
            **self.extra_meta
        })

        self._flush()

    def close(self, duration: float, message_count: int, cost_usd: float, success: bool = True, error: Optional[str] = None):
        """Close both log files with session summary."""
        if not self._log_handle or not self._jsonl_handle:
            return

        # Write human-readable footer
        self._log_handle.write(f"\n{'='*80}\n")
        self._log_handle.write(f"{'COMPLETED' if success else 'FAILED'}\n")
        self._log_handle.write(f"Duration: {duration:.1f}s | Messages: {message_count} | Cost: ${cost_usd:.4f}\n")
        if error:
            self._log_handle.write(f"Error: {error}\n")
        self._log_handle.write(f"{'='*80}\n")

        # Write JSONL session_end
        self._write_jsonl({
            "type": "session_end",
            "ts": self._get_ts(),
            "seq": self._next_seq(),
            "success": success,
            "duration_seconds": duration,
            "message_count": message_count,
            "cost_usd": cost_usd,
            "error": error
        })

        self._flush()
        self._log_handle.close()
        self._jsonl_handle.close()
        self._log_handle = None
        self._jsonl_handle = None

    def log_app(self, message: str, level: str = "info"):
        """
        Log application/program message (not from SDK).

        Args:
            message: Log message
            level: Log level (info, warn, error, debug)
        """
        ts = self._get_ts()
        seq = self._next_seq()

        # Human-readable
        self._write_log(f"[{ts}] [{seq}] APP ({level.upper()}): {message}")

        # JSONL
        self._write_jsonl({
            "type": "app",
            "ts": ts,
            "seq": seq,
            "level": level,
            "message": message
        })

        self._flush()

    def log_message(self, message: Any):
        """
        Log a Claude Agent SDK message.

        Handles all Message Types:
        - UserMessage
        - AssistantMessage
        - SystemMessage
        - ResultMessage
        - StreamEvent (if present)
        """
        ts = self._get_ts()

        if isinstance(message, AssistantMessage):
            self._log_assistant_message(message, ts)
        elif isinstance(message, UserMessage):
            self._log_user_message(message, ts)
        elif isinstance(message, SystemMessage):
            self._log_system_message(message, ts)
        elif isinstance(message, ResultMessage):
            self._log_result_message(message, ts)
        else:
            # Handle StreamEvent or unknown types
            type_name = type(message).__name__
            if type_name == "StreamEvent":
                self._log_stream_event(message, ts)
            else:
                self._log_unknown_message(message, ts)

        self._flush()

    def _log_assistant_message(self, message: AssistantMessage, ts: str):
        """Log AssistantMessage with all content blocks (with redaction)."""
        model = getattr(message, 'model', 'unknown')

        for block in message.content:
            seq = self._next_seq()

            if isinstance(block, TextBlock):
                text_content, redacted = self._redact_if_sensitive(block.text)

                # Human-readable
                self._write_log(f"[{ts}] [{seq}] ASSISTANT TEXT:\n{text_content}\n{'-'*40}")

                # JSONL
                self._write_jsonl({
                    "type": "assistant_text",
                    "ts": ts,
                    "seq": seq,
                    "model": model,
                    "content": text_content,
                    "redacted": redacted
                })

            elif isinstance(block, ThinkingBlock):
                thinking = getattr(block, 'thinking', '')
                thinking_content, redacted = self._redact_if_sensitive(thinking)

                # Human-readable
                if not redacted:
                    preview = thinking[:200] + "..." if len(thinking) > 200 else thinking
                else:
                    preview = thinking_content
                self._write_log(f"[{ts}] [{seq}] THINKING:\n{preview}\n{'-'*40}")

                # JSONL
                self._write_jsonl({
                    "type": "assistant_thinking",
                    "ts": ts,
                    "seq": seq,
                    "model": model,
                    "content": thinking_content,
                    "redacted": redacted
                })

            elif isinstance(block, ToolUseBlock):
                tool_name = getattr(block, 'name', 'unknown')
                tool_id = getattr(block, 'id', '')
                tool_input = getattr(block, 'input', {})

                input_str, redacted = self._redact_if_sensitive(tool_input)
                if not redacted and isinstance(tool_input, dict):
                    input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)

                # Human-readable
                self._write_log(f"[{ts}] [{seq}] TOOL CALL: {tool_name}\nID: {tool_id}\nInput:\n{input_str}\n{'-'*40}")

                # JSONL
                self._write_jsonl({
                    "type": "tool_call",
                    "ts": ts,
                    "seq": seq,
                    "model": model,
                    "tool": tool_name,
                    "tool_use_id": tool_id,
                    "input": input_str if redacted else tool_input,
                    "redacted": redacted
                })

            elif isinstance(block, ToolResultBlock):
                tool_use_id = getattr(block, 'tool_use_id', '')
                content = getattr(block, 'content', '')
                is_error = getattr(block, 'is_error', False)

                content_str, redacted = self._redact_if_sensitive(content)
                if not redacted:
                    content_str = self._truncate_content(content)

                # Human-readable
                display_str = content_str if redacted else content_str[:500]
                self._write_log(f"[{ts}] [{seq}] TOOL RESULT (in assistant): {tool_use_id[:12]}...\nError: {is_error}\nOutput:\n{display_str}\n{'-'*40}")

                # JSONL
                self._write_jsonl({
                    "type": "tool_result",
                    "ts": ts,
                    "seq": seq,
                    "model": model,
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "output": content_str,
                    "redacted": redacted
                })

            else:
                # Unknown block type
                block_type = type(block).__name__
                block_data, redacted = self._redact_if_sensitive(str(block)[:500])

                self._write_log(f"[{ts}] [{seq}] UNKNOWN BLOCK ({block_type}):\n{block_data}\n{'-'*40}")

                self._write_jsonl({
                    "type": "unknown_block",
                    "ts": ts,
                    "seq": seq,
                    "model": model,
                    "block_type": block_type,
                    "raw": block_data,
                    "redacted": redacted
                })

    def _log_user_message(self, message: UserMessage, ts: str):
        """Log UserMessage with all content blocks (with redaction)."""
        content = getattr(message, 'content', None)

        if content is None:
            return

        # UserMessage.content can be str or list[ContentBlock]
        if isinstance(content, str):
            seq = self._next_seq()
            content_str, redacted = self._redact_if_sensitive(content)

            # Human-readable
            self._write_log(f"[{ts}] [{seq}] USER:\n{content_str}\n{'-'*40}")

            # JSONL
            self._write_jsonl({
                "type": "user_message",
                "ts": ts,
                "seq": seq,
                "content": content_str,
                "redacted": redacted
            })

        elif isinstance(content, list):
            for block in content:
                seq = self._next_seq()

                if isinstance(block, TextBlock):
                    text_content, redacted = self._redact_if_sensitive(block.text)

                    # Human-readable
                    self._write_log(f"[{ts}] [{seq}] USER TEXT:\n{text_content}\n{'-'*40}")

                    # JSONL
                    self._write_jsonl({
                        "type": "user_text",
                        "ts": ts,
                        "seq": seq,
                        "content": text_content,
                        "redacted": redacted
                    })

                elif isinstance(block, ToolResultBlock):
                    tool_use_id = getattr(block, 'tool_use_id', '')
                    content_data = getattr(block, 'content', '')
                    is_error = getattr(block, 'is_error', False)

                    content_str, redacted = self._redact_if_sensitive(content_data)
                    if not redacted:
                        content_str = self._truncate_content(content_data)

                    # Human-readable
                    status = "ERROR" if is_error else "OK"
                    display_str = content_str if redacted else content_str[:1000]
                    self._write_log(f"[{ts}] [{seq}] TOOL RESULT [{status}]: {tool_use_id[:12]}...\nOutput:\n{display_str}\n{'-'*40}")

                    # JSONL
                    self._write_jsonl({
                        "type": "tool_result",
                        "ts": ts,
                        "seq": seq,
                        "tool_use_id": tool_use_id,
                        "is_error": is_error,
                        "output": content_str,
                        "redacted": redacted
                    })

                else:
                    # Unknown block in UserMessage
                    block_type = type(block).__name__
                    block_data, redacted = self._redact_if_sensitive(str(block)[:500])

                    self._write_log(f"[{ts}] [{seq}] USER BLOCK ({block_type}):\n{block_data}\n{'-'*40}")

                    self._write_jsonl({
                        "type": "user_block",
                        "ts": ts,
                        "seq": seq,
                        "block_type": block_type,
                        "raw": block_data,
                        "redacted": redacted
                    })

    def _is_sensitive_content(self, content: str) -> bool:
        """Check if content contains sensitive prompt patterns."""
        if not content:
            return False
        return any(pattern in content for pattern in self.SENSITIVE_PROMPT_PATTERNS)

    def _redact_if_sensitive(self, content: Any) -> tuple[str, bool]:
        """
        Check and redact sensitive content.
        Returns (content_str, was_redacted).
        """
        if content is None:
            return "", False

        if isinstance(content, dict):
            content_str = json.dumps(content, ensure_ascii=False, default=str)
        elif isinstance(content, list):
            content_str = json.dumps(content, ensure_ascii=False, default=str)
        else:
            content_str = str(content)

        if self._is_sensitive_content(content_str):
            return f"[PROMPT REDACTED: {len(content_str)} chars]", True

        return content_str, False

    def _log_system_message(self, message: SystemMessage, ts: str):
        """Log SystemMessage with prompt redaction."""
        seq = self._next_seq()
        subtype = getattr(message, 'subtype', 'unknown')
        data = getattr(message, 'data', {})

        # Check and redact sensitive prompts
        data_str, was_redacted = self._redact_if_sensitive(data)
        if not was_redacted and isinstance(data, dict):
            data_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Human-readable
        self._write_log(f"[{ts}] [{seq}] SYSTEM ({subtype}):\n{data_str}\n{'-'*40}")

        # JSONL
        self._write_jsonl({
            "type": "system",
            "ts": ts,
            "seq": seq,
            "subtype": subtype,
            "data": data_str if was_redacted else data,
            "redacted": was_redacted
        })

    def _log_result_message(self, message: ResultMessage, ts: str):
        """Log ResultMessage (with redaction)."""
        seq = self._next_seq()

        subtype = getattr(message, 'subtype', 'unknown')
        duration_ms = getattr(message, 'duration_ms', 0)
        duration_api_ms = getattr(message, 'duration_api_ms', 0)
        is_error = getattr(message, 'is_error', False)
        num_turns = getattr(message, 'num_turns', 0)
        session_id = getattr(message, 'session_id', '')
        total_cost_usd = getattr(message, 'total_cost_usd', None)
        usage = getattr(message, 'usage', None)
        result = getattr(message, 'result', None)
        structured_output = getattr(message, 'structured_output', None)

        # Check redaction for result and structured_output
        result_str, result_redacted = self._redact_if_sensitive(result) if result else ("", False)
        output_str, output_redacted = self._redact_if_sensitive(structured_output) if structured_output else ("", False)
        any_redacted = result_redacted or output_redacted

        # Human-readable
        self._write_log(f"[{ts}] [{seq}] RESULT ({subtype}):")
        self._write_log(f"  Session: {session_id[:12]}... | Turns: {num_turns} | Error: {is_error}")
        self._write_log(f"  Duration: {duration_ms}ms (API: {duration_api_ms}ms)")
        if total_cost_usd is not None:
            self._write_log(f"  Cost: ${total_cost_usd:.4f}")
        if usage:
            self._write_log(f"  Usage: {json.dumps(usage)}")
        if result:
            if result_redacted:
                self._write_log(f"  Result:\n{result_str}")
            else:
                result_preview = result[:500] + "..." if len(result) > 500 else result
                self._write_log(f"  Result:\n{result_preview}")
        if structured_output:
            if output_redacted:
                self._write_log(f"  Structured Output: {output_str}")
            else:
                self._write_log(f"  Structured Output: {json.dumps(structured_output, ensure_ascii=False)[:500]}")
        self._write_log(f"{'='*40}")

        # JSONL
        self._write_jsonl({
            "type": "result",
            "ts": ts,
            "seq": seq,
            "subtype": subtype,
            "session_id": session_id,
            "is_error": is_error,
            "num_turns": num_turns,
            "duration_ms": duration_ms,
            "duration_api_ms": duration_api_ms,
            "cost_usd": total_cost_usd,
            "usage": usage,
            "result": result_str if result_redacted else result,
            "structured_output": output_str if output_redacted else structured_output,
            "redacted": any_redacted
        })

    def _log_stream_event(self, message: Any, ts: str):
        """Log StreamEvent (with redaction)."""
        seq = self._next_seq()

        uuid = getattr(message, 'uuid', '')
        session_id = getattr(message, 'session_id', '')
        event = getattr(message, 'event', {})
        parent_tool_use_id = getattr(message, 'parent_tool_use_id', None)

        # Check redaction for event
        event_str, redacted = self._redact_if_sensitive(event)

        # Human-readable (abbreviated)
        event_type = event.get('type', 'unknown') if isinstance(event, dict) else 'unknown'
        self._write_log(f"[{ts}] [{seq}] STREAM ({event_type}): {uuid[:8]}...")

        # JSONL
        self._write_jsonl({
            "type": "stream_event",
            "ts": ts,
            "seq": seq,
            "uuid": uuid,
            "session_id": session_id,
            "event_type": event_type,
            "event": event_str if redacted else event,
            "parent_tool_use_id": parent_tool_use_id,
            "redacted": redacted
        })

    def _log_unknown_message(self, message: Any, ts: str):
        """Log unknown message type (with redaction)."""
        seq = self._next_seq()
        msg_type = type(message).__name__
        msg_str, redacted = self._redact_if_sensitive(str(message)[:1000])

        # Human-readable
        self._write_log(f"[{ts}] [{seq}] UNKNOWN MESSAGE ({msg_type}):\n{msg_str}\n{'-'*40}")

        # JSONL
        self._write_jsonl({
            "type": "unknown",
            "ts": ts,
            "seq": seq,
            "message_type": msg_type,
            "raw": msg_str,
            "redacted": redacted
        })

    def log_error(self, error: str):
        """Log an error message."""
        ts = self._get_ts()
        seq = self._next_seq()

        # Human-readable
        self._write_log(f"[{ts}] [{seq}] ERROR:\n{error}\n{'='*40}")

        # JSONL
        self._write_jsonl({
            "type": "error",
            "ts": ts,
            "seq": seq,
            "message": error
        })

        self._flush()

    def _write_log(self, text: str):
        """Write to human-readable log."""
        if self._log_handle:
            self._log_handle.write(text + "\n")

    def _write_jsonl(self, entry: dict):
        """Write to JSONL file."""
        if self._jsonl_handle:
            self._jsonl_handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def _flush(self):
        """Flush both file handles."""
        if self._log_handle:
            self._log_handle.flush()
        if self._jsonl_handle:
            self._jsonl_handle.flush()

    def _get_ts(self) -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%H:%M:%S")

    def _next_seq(self) -> int:
        """Get next sequence number."""
        self._seq += 1
        return self._seq

    def _truncate_content(self, content: Any, max_len: int = 10000) -> str:
        """Truncate content to max length."""
        if content is None:
            return ""

        if isinstance(content, str):
            content_str = content
        elif isinstance(content, list):
            # Handle list of content items (e.g., from ToolResultBlock)
            try:
                content_str = json.dumps(content, ensure_ascii=False, default=str)
            except:
                content_str = str(content)
        else:
            content_str = str(content)

        if len(content_str) > max_len:
            return content_str[:max_len] + f"\n... [truncated, total {len(content_str)} chars]"
        return content_str

    @property
    def sequence(self) -> int:
        """Current sequence number."""
        return self._seq
