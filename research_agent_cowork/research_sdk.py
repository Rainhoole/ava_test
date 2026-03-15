#!/usr/bin/env python3
"""
Research Agent using Claude Agent SDK (方案1: MCP模式)

Uses Claude Agent SDK with:
- Built-in tools: WebSearch, WebFetch, Write
- Custom MCP server: twitter_mcp.py for Twitter tools
- Auto-permissions: bypassPermissions mode

Usage:
    python research_sdk.py @username
    python research_sdk.py @username --output report.md
"""

import os
import sys
import asyncio
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv('../.env')
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Enable debug logging
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Also enable SDK logging
logging.getLogger('claude_agent_sdk').setLevel(logging.DEBUG)

# Try to import Claude Agent SDK
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


def load_vc_prompt(max_length: int = 0) -> str:
    """Load the complete VC research prompt.

    Args:
        max_length: If > 0, truncate prompt to this length
    """
    prompt_path = Path(__file__).parent.parent / "research_agent" / "research_agent_prompt_al.md"
    if prompt_path.exists():
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"Loaded system prompt: {len(content)} chars from {prompt_path}")
        if max_length > 0 and len(content) > max_length:
            content = content[:max_length] + "\n\n[TRUNCATED]"
            logger.warning(f"System prompt truncated to {max_length} chars")
        return content
    else:
        logger.warning(f"VC prompt not found at {prompt_path}, using fallback")
        return get_fallback_prompt()


def truncate_text(text: str, head_words: int = 20, tail_words: int = 20) -> str:
    """Truncate text to show first N and last N words with ellipsis."""
    words = text.split()
    if len(words) <= head_words + tail_words:
        return text
    head = ' '.join(words[:head_words])
    tail = ' '.join(words[-tail_words:])
    return f"{head} ... [{len(words) - head_words - tail_words} words] ... {tail}"


class CostTracker:
    """Track API costs per step and total."""

    # Pricing per 1K tokens (adjust as needed)
    PRICING = {
        "input": 0.015,           # $15/1M input tokens
        "output": 0.075,          # $75/1M output tokens
        "cache_read": 0.00375,    # $3.75/1M cache read tokens
        "cache_create": 0.01875,  # $18.75/1M cache creation tokens
    }

    def __init__(self):
        self.processed_message_ids = set()
        self.step_usages = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_create_tokens = 0

    def process_message(self, message, message_count: int = 0) -> Optional[dict]:
        """Process a message and track its usage. Returns usage dict if new."""
        # Only process AssistantMessage with usage
        if not hasattr(message, 'usage') or message.usage is None:
            return None

        # Get message ID to avoid duplicates
        message_id = getattr(message, 'id', None)
        if not message_id:
            # Try to get from nested message
            if hasattr(message, 'message') and hasattr(message.message, 'id'):
                message_id = message.message.id

        if not message_id or message_id in self.processed_message_ids:
            return None

        # Mark as processed
        self.processed_message_ids.add(message_id)

        # Extract usage - handle both dict and object formats
        usage = message.usage
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_create = usage.get("cache_creation_input_tokens", 0)
        else:
            # Handle object with attributes
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

        # Update totals
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_create_tokens += cache_create

        # Calculate step cost
        step_cost = self.calculate_cost(usage)

        step_data = {
            "step": message_count,
            "message_id": message_id[:12] + "..." if message_id and len(message_id) > 12 else message_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_create_tokens": cache_create,
            "cost_usd": step_cost
        }
        self.step_usages.append(step_data)
        return step_data

    def calculate_cost(self, usage) -> float:
        """Calculate cost for a usage dict or object."""
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_create = usage.get("cache_creation_input_tokens", 0)
        else:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

        cost = (
            (input_tokens / 1000) * self.PRICING["input"] +
            (output_tokens / 1000) * self.PRICING["output"] +
            (cache_read / 1000) * self.PRICING["cache_read"] +
            (cache_create / 1000) * self.PRICING["cache_create"]
        )
        return cost

    def set_sdk_cost(self, total_cost_usd: float):
        """Set the SDK-reported total cost for comparison."""
        self.sdk_total_cost = total_cost_usd

    def get_total_cost(self) -> float:
        """Get total cost so far."""
        return sum(step["cost_usd"] for step in self.step_usages)

    def get_summary(self) -> dict:
        """Get usage summary."""
        return {
            "steps": len(self.step_usages),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_create_tokens": self.total_cache_create_tokens,
            "total_cost_usd": self.get_total_cost()
        }

    def print_detailed_report(self, sdk_cost: float = None):
        """Print detailed cost report with per-message and total breakdown."""
        print("\n" + "=" * 70)
        print("💰 COST DETAILED REPORT")
        print("=" * 70)

        # Per-message breakdown
        if self.step_usages:
            print("\n📊 Per-Message Token Usage:")
            print("-" * 70)
            print(f"{'Step':<6} {'Input':<10} {'Output':<10} {'CacheRead':<12} {'CacheCreate':<12} {'Cost USD':<10}")
            print("-" * 70)

            for step in self.step_usages:
                print(f"{step['step']:<6} {step['input_tokens']:<10} {step['output_tokens']:<10} "
                      f"{step['cache_read_tokens']:<12} {step['cache_create_tokens']:<12} "
                      f"${step['cost_usd']:.4f}")

            # Total summary
            print("-" * 70)
            print(f"{'TOTAL':<6} {self.total_input_tokens:<10} {self.total_output_tokens:<10} "
                  f"{self.total_cache_read_tokens:<12} {self.total_cache_create_tokens:<12} "
                  f"${self.get_total_cost():.4f}")
        else:
            print("\n⚠️ No per-message token data available from SDK")
            print("   (SDK may not expose individual message usage)")

        # Cost breakdown by token type
        print("\n💵 Cost Breakdown by Token Type:")
        print("-" * 70)
        input_cost = (self.total_input_tokens / 1000) * self.PRICING["input"]
        output_cost = (self.total_output_tokens / 1000) * self.PRICING["output"]
        cache_read_cost = (self.total_cache_read_tokens / 1000) * self.PRICING["cache_read"]
        cache_create_cost = (self.total_cache_create_tokens / 1000) * self.PRICING["cache_create"]

        print(f"  Input tokens:        {self.total_input_tokens:>12} × $0.015/1K = ${input_cost:.4f}")
        print(f"  Output tokens:       {self.total_output_tokens:>12} × $0.075/1K = ${output_cost:.4f}")
        print(f"  Cache read tokens:   {self.total_cache_read_tokens:>12} × $0.00375/1K = ${cache_read_cost:.4f}")
        print(f"  Cache create tokens: {self.total_cache_create_tokens:>12} × $0.01875/1K = ${cache_create_cost:.4f}")
        print("-" * 70)

        tracked_cost = self.get_total_cost()
        if sdk_cost and sdk_cost > 0:
            print(f"  Tracked Cost:    ${tracked_cost:.4f}")
            print(f"  SDK Total Cost:  ${sdk_cost:.4f} ⬅️ (from ResultMessage)")
            print("-" * 70)
            print(f"  💵 FINAL COST: ${sdk_cost:.4f}")
        else:
            print(f"  TOTAL COST: ${tracked_cost:.4f}")
        print("=" * 70 + "\n")


def get_fallback_prompt() -> str:
    """Fallback prompt if main file not available."""
    return """You are an elite Venture Capital Analyst at a top-tier pre-seed and seed-stage technology investment firm.

Your mission: Identify companies with 1000x potential from minimal social media signals.

## Research Process
1. Get Twitter profile - check Early Exit conditions
2. Get tweets and following list
3. Scrape website and docs using WebFetch
4. Search web for additional info using WebSearch
5. Generate comprehensive report

## Early Exit Conditions
- Foundation/Non-profit
- Regional community account
- Non-blockchain/Non-AI project
- Inactive (>18 months no activity)
- Later stage (>$5M raised)

## Report Structure
1. Project Overview
2. Technology & Products
3. Team & Backers
4. Market & Traction
5. Competitive Landscape
6. Timeline & Milestones
7. Risks & Challenges
8. Conclusion & Outlook

## Scoring (100 points)
- Founder Pattern: 25 pts
- Idea Pattern: 35 pts
- Structural Advantage: 35 pts
- Asymmetric Signals: 5 pts

Priority: High (80+), Medium (60-79), Low (<60)
"""


class ResearchAgent:
    """
    Research Agent using Claude Agent SDK.

    Architecture:
    - MCP Server: twitter_mcp.py provides Twitter tools
    - Built-in: WebSearch, WebFetch for web research
    - Built-in: Write for saving reports
    - Permissions: bypassPermissions (auto-approve all)
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929", use_system_prompt: bool = True):
        self.model = model
        if use_system_prompt:
            self.system_prompt = load_vc_prompt()
        else:
            self.system_prompt = get_fallback_prompt()
            logger.info("Using fallback system prompt")

        # Output directory
        self.output_dir = Path(__file__).parent / "outputs" / datetime.now().strftime("%Y%m%d")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # MCP server paths
        self.twitter_mcp_path = Path(__file__).parent / "twitter_mcp.py"
        self.firecrawl_mcp_path = Path(__file__).parent / "firecrawl_mcp.py"

        if not self.twitter_mcp_path.exists():
            raise FileNotFoundError(f"Twitter MCP server not found: {self.twitter_mcp_path}")
        if not self.firecrawl_mcp_path.exists():
            raise FileNotFoundError(f"Firecrawl MCP server not found: {self.firecrawl_mcp_path}")

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def research(self, twitter_handle: str) -> Optional[str]:
        """
        Perform complete research using Claude Agent SDK.

        Args:
            twitter_handle: Twitter username to research

        Returns:
            Complete research report or None if failed
        """
        clean_handle = twitter_handle.replace('@', '')
        logger.info(f"{'='*60}")
        logger.info(f"Research Agent (Claude SDK): Researching @{clean_handle}")
        logger.info(f"{'='*60}")

        start_time = datetime.now()
        output_file = self.output_dir / f"{clean_handle}_research.md"
        log_file = self.output_dir / f"{clean_handle}_messages.log"

        # Build the research prompt
        user_prompt = f"""Research the Twitter profile @{clean_handle}."""

        try:
            report_content = []
            message_count = 0
            cost_tracker = CostTracker()
            sdk_final_cost = 0.0  # Track SDK-reported cost

            # Open log file for writing messages
            msg_log = open(log_file, 'w', encoding='utf-8')
            msg_log.write(f"{'='*80}\n")
            msg_log.write(f"Research Agent Message Log\n")
            msg_log.write(f"Target: @{clean_handle}\n")
            msg_log.write(f"Started: {start_time.isoformat()}\n")
            msg_log.write(f"Model: {self.model}\n")
            msg_log.write(f"{'='*80}\n\n")

            # Stderr callback for debugging
            def stderr_handler(line: str):
                logger.debug(f"[CLI stderr] {line}")

            # Configure Claude Agent SDK options
            options = ClaudeAgentOptions(
                # Built-in tools for web research and file operations
                allowed_tools=[
                    "WebSearch",   # Built-in web search
                    "WebFetch",    # Built-in web scraping
                    "Write",       # Save report to file
                    "Read",        # Read files if needed
                ],
                # Auto-approve all permissions
                permission_mode="bypassPermissions",
                # MCP servers for Twitter and Firecrawl tools
                mcp_servers={
                    "twitter": {
                        "command": "python",
                        "args": [str(self.twitter_mcp_path)]
                    },
                    "firecrawl": {
                        "command": "python",
                        "args": [str(self.firecrawl_mcp_path)]
                    }
                },
                # System prompt with VC research methodology
                system_prompt=self.system_prompt,
                # Working directory
                cwd=str(self.output_dir),
                # Model selection
                model=self.model,
                # Debug: capture stderr from CLI
                stderr=stderr_handler,
            )

            logger.info(f"Starting agent with model: {self.model}")
            logger.info(f"MCP servers: Twitter={self.twitter_mcp_path}, Firecrawl={self.firecrawl_mcp_path}")
            logger.info(f"Output directory: {self.output_dir}")
            logger.info(f"System prompt length: {len(self.system_prompt)} chars")
            logger.info(f"User prompt length: {len(user_prompt)} chars")
            sys.stdout.flush()  # Ensure output is visible

            logger.info("Calling query()...")
            sys.stdout.flush()

            # Run the agent
            async for message in query(
                prompt=user_prompt,
                options=options
            ):
                message_count += 1

                # Track cost for this message
                step_usage = cost_tracker.process_message(message, message_count)
                if step_usage:
                    logger.debug(f"[{message_count}] Cost: ${step_usage['cost_usd']:.4f} "
                                f"(in:{step_usage['input_tokens']}, out:{step_usage['output_tokens']})")

                # Debug: log usage data structure if present
                if hasattr(message, 'usage') and message.usage is not None:
                    logger.debug(f"[{message_count}] Usage data type: {type(message.usage)}, value: {message.usage}")

                # Get current timestamp for log
                ts = datetime.now().strftime("%H:%M:%S")

                # Handle different message types using isinstance
                if isinstance(message, AssistantMessage):
                    # Process assistant message content blocks
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text
                            # Print truncated version (first 20 + last 20 words)
                            truncated = truncate_text(text, head_words=20, tail_words=20)
                            logger.info(f"[{message_count}] Assistant: {truncated[:150]}...")
                            print(f"💬 [{message_count}] Assistant: {truncated}")
                            # Write full content to log
                            msg_log.write(f"[{ts}] [{message_count}] ASSISTANT TEXT:\n")
                            msg_log.write(f"{text}\n")
                            msg_log.write(f"{'-'*40}\n\n")
                        elif isinstance(block, ToolUseBlock):
                            # Print tool call with input parameters summary
                            tool_input = block.input if hasattr(block, 'input') else {}
                            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False) if isinstance(tool_input, dict) else str(tool_input)
                            input_summary = str(tool_input)[:100] + "..." if len(str(tool_input)) > 100 else str(tool_input)
                            logger.info(f"[{message_count}] Tool Call: {block.name} | Input: {input_summary}")
                            print(f"🔧 [{message_count}] Tool Call: {block.name}")
                            print(f"   📥 Input: {input_summary}")
                            # Write full content to log
                            msg_log.write(f"[{ts}] [{message_count}] TOOL CALL: {block.name}\n")
                            msg_log.write(f"Input:\n{input_str}\n")
                            msg_log.write(f"{'-'*40}\n\n")

                elif isinstance(message, ResultMessage):
                    # Capture SDK's total cost
                    if message.total_cost_usd:
                        sdk_final_cost = message.total_cost_usd
                    final_cost = message.total_cost_usd or cost_tracker.get_total_cost()
                    logger.info(f"[{message_count}] Result: subtype={message.subtype}, "
                               f"duration={message.duration_ms}ms, turns={message.num_turns}, "
                               f"cost=${final_cost:.4f}")
                    print(f"✅ [{message_count}] Result: {message.subtype} | Duration: {message.duration_ms}ms | Turns: {message.num_turns} | Cost: ${final_cost:.4f}")
                    if message.result:
                        result_truncated = truncate_text(message.result, head_words=30, tail_words=30)
                        print(f"   📄 Result: {result_truncated}")
                        report_content.append(message.result)
                    # Write to log
                    msg_log.write(f"[{ts}] [{message_count}] RESULT: {message.subtype}\n")
                    msg_log.write(f"Duration: {message.duration_ms}ms | Turns: {message.num_turns} | Cost: ${final_cost:.4f}\n")
                    if message.result:
                        msg_log.write(f"Result:\n{message.result}\n")
                    msg_log.write(f"{'='*40}\n\n")

                elif isinstance(message, SystemMessage):
                    logger.info(f"[{message_count}] System: subtype={message.subtype}")
                    data_summary = str(message.data)[:100] + "..." if len(str(message.data)) > 100 else str(message.data)
                    print(f"⚙️ [{message_count}] System: {message.subtype}")
                    print(f"   📋 Data: {data_summary}")
                    # Write to log
                    data_str = json.dumps(message.data, indent=2, ensure_ascii=False) if isinstance(message.data, dict) else str(message.data)
                    msg_log.write(f"[{ts}] [{message_count}] SYSTEM: {message.subtype}\n")
                    msg_log.write(f"Data:\n{data_str}\n")
                    msg_log.write(f"{'-'*40}\n\n")

                elif isinstance(message, UserMessage):
                    # Tool results come back as UserMessage
                    logger.debug(f"[{message_count}] UserMessage (tool result)")
                    # Print tool result summary
                    if hasattr(message, 'content') and message.content:
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                tool_id = getattr(block, 'tool_use_id', 'unknown')[:12]
                                content = str(block.content) if hasattr(block, 'content') else str(block)
                                content_truncated = truncate_text(content, head_words=20, tail_words=20)
                                print(f"📤 [{message_count}] Tool Result ({tool_id}...)")
                                print(f"   📋 Output: {content_truncated}")
                                # Write full content to log
                                msg_log.write(f"[{ts}] [{message_count}] TOOL RESULT: {tool_id}...\n")
                                msg_log.write(f"Output:\n{content}\n")
                                msg_log.write(f"{'-'*40}\n\n")
                            else:
                                # Other content in UserMessage
                                block_str = str(block)[:150] + "..." if len(str(block)) > 150 else str(block)
                                print(f"👤 [{message_count}] UserMessage: {block_str}")
                                msg_log.write(f"[{ts}] [{message_count}] USER MESSAGE:\n{str(block)}\n{'-'*40}\n\n")

                else:
                    # Unknown message type - still print summary
                    logger.debug(f"[{message_count}] Unknown message type: {type(message)}")
                    msg_str = str(message)[:150] + "..." if len(str(message)) > 150 else str(message)
                    print(f"❓ [{message_count}] {type(message).__name__}: {msg_str}")
                    msg_log.write(f"[{ts}] [{message_count}] UNKNOWN: {type(message).__name__}\n{str(message)}\n{'-'*40}\n\n")

                sys.stdout.flush()

            elapsed = (datetime.now() - start_time).total_seconds()

            # Print detailed cost report with SDK cost
            cost_tracker.print_detailed_report(sdk_cost=sdk_final_cost)

            # Compile report
            report = "\n".join(filter(None, report_content))

            # Get cost summary for metadata
            cost_summary = cost_tracker.get_summary()
            final_cost = sdk_final_cost if sdk_final_cost > 0 else cost_summary['total_cost_usd']

            # Add metadata header
            report_with_meta = f"""# Research Report: @{clean_handle}
Generated: {datetime.now().isoformat()}
Method: Claude Agent SDK (MCP Mode)
Model: {self.model}
Duration: {elapsed:.1f}s
Messages: {message_count}
Total Cost: ${final_cost:.4f}
Tokens: input={cost_summary['total_input_tokens']}, output={cost_summary['total_output_tokens']}, cache_read={cost_summary['total_cache_read_tokens']}, cache_create={cost_summary['total_cache_create_tokens']}

---

{report}
"""

            # Save report
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_with_meta)

            logger.info(f"\n{'='*60}")
            logger.info(f"Research complete!")
            logger.info(f"Report saved: {output_file}")
            logger.info(f"Duration: {elapsed:.1f}s")
            logger.info(f"Messages: {message_count}")
            logger.info(f"Total Cost: ${final_cost:.4f}")
            logger.info(f"{'='*60}")

            return report_with_meta

        except Exception as e:
            logger.error(f"Research failed: {e}")
            import traceback
            traceback.print_exc()
            return None


async def main_async():
    parser = argparse.ArgumentParser(
        description='VC Research Agent - Claude Agent SDK (MCP Mode)'
    )
    parser.add_argument(
        'twitter_handle',
        type=str,
        help='Twitter handle to research (e.g., @username)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (optional, auto-generated if not provided)'
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
         default='claude-opus-4-5-20251101',
        help='Model to use (default: claude-opus-4-5-20251101)'
    )
    parser.add_argument(
        '--no-system-prompt',
        action='store_true',
        help='Disable system prompt (use fallback for testing)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable extra debug output'
    )

    args = parser.parse_args()

    # Set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check for API key
    if not os.getenv('ANTHROPIC_API_KEY'):
        logger.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # Check for RapidAPI key (for Twitter tools)
    if not os.getenv('RAPID_API_KEY'):
        logger.warning("RAPID_API_KEY not set - Twitter tools may not work")

    # Run research
    agent = ResearchAgent(
        model=args.model,
        use_system_prompt=not args.no_system_prompt
    )
    report = await agent.research(args.twitter_handle)

    if report:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"Report also saved to: {args.output}")

        print("\n" + "="*60)
        print("REPORT PREVIEW (first 2000 chars):")
        print("="*60)
        print(report[:2000])
    else:
        logger.error("Research failed")
        sys.exit(1)


def main():
    """Entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
