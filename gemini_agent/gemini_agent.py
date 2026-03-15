"""
Lightweight Gemini research agent that reuses the existing research prompt
and tools from `mcp_server/tools.py`. Intended for quick manual testing of
Gemini 3 Pro with web + function tools (no production hardening).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

try:
    import google.genai as genai_search  # type: ignore
    from google.genai import types as genai_search_types  # type: ignore
except ImportError:
    genai_search = None
    genai_search_types = None

# Ensure repository root is on sys.path for relative imports
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import google.generativeai as genai  # type: ignore
    from google.generativeai import types as genai_types  # type: ignore
except ImportError:
    genai = None
    genai_types = None

# Reuse the existing Python tool implementations
from mcp_server.tools import Tools

# Inline override for quick testing (paste your key here)
INLINE_GEMINI_API_KEY = "AIzaSyC9oYXREySbYI1PQTqGYhspnimmp7_IEuo"  # paste key here for local testing


def load_system_prompt(prompt_path: Optional[str] = None) -> str:
    """Load base research prompt and append Gemini-specific instructions."""
    if prompt_path:
        base = Path(prompt_path).read_text(encoding="utf-8")
    else:
        base_path = Path(__file__).resolve().parent.parent / "research_agent" / "research_agent_prompt_al.md"
        base = base_path.read_text(encoding="utf-8")

    appendix_path = Path(__file__).resolve().parent / "gemini_prompt_appendix.md"
    if appendix_path.exists():
        appendix = appendix_path.read_text(encoding="utf-8")
        return base + "\n\n---\n\n" + appendix
    return base


class GeminiResearchAgent:
    """Minimal research runner using Gemini with the existing prompt and tools."""

    def __init__(
        self,
        model: str = "gemini-3-pro-preview",
        prompt_path: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ):
        if genai is None:
            raise ImportError("google-generativeai is required. Install with `pip install google-generativeai`.")

        load_dotenv()
        self.model = model
        self.system_prompt = load_system_prompt(prompt_path)
        self.api_key = (
            gemini_api_key
            or INLINE_GEMINI_API_KEY
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment.")

        genai.configure(api_key=self.api_key)
        self.tools_impl = Tools()
        self.function_specs = self._build_function_specs()

    def _run_google_search(self, query: str) -> str:
        """Run Google Search grounding via google-genai (gemini-2.5-flash)."""
        if genai_search is None:
            return ""
        try:
            print(f"[SEARCH] Starting Google Search grounding for query (len={len(query)} chars)")
            client = genai_search.Client(api_key=self.api_key)
            grounding_tool = genai_search_types.Tool(
                google_search=genai_search_types.GoogleSearch()
            )
            config = genai_search_types.GenerateContentConfig(tools=[grounding_tool])
            start = time.time()
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=query,
                config=config,
            )
            text = response.text or ""
            max_chars = 60000
            if len(text) > max_chars:
                print(f"[SEARCH] Truncating search context from {len(text)} to {max_chars} chars")
                text = text[:max_chars]
            elapsed = time.time() - start
            print(f"[SEARCH] Google Search grounding completed in {elapsed:.1f}s (len={len(text)} chars)")
            return text
        except Exception as e:
            print(f"[SEARCH] Google Search grounding failed: {type(e).__name__}: {e}")
            return ""

    # ------------------------------------------------------------------ #
    # Tool setup
    # ------------------------------------------------------------------ #
    def _build_function_specs(self) -> List[Dict[str, Any]]:
        """Return function declaration dicts for Gemini function-calling."""

        def s_string(description: Optional[str] = None) -> Dict[str, Any]:
            out: Dict[str, Any] = {"type": "string"}
            if description:
                out["description"] = description
            return out

        def s_integer(description: Optional[str] = None) -> Dict[str, Any]:
            out: Dict[str, Any] = {"type": "integer"}
            if description:
                out["description"] = description
            return out

        def s_boolean(description: Optional[str] = None) -> Dict[str, Any]:
            out: Dict[str, Any] = {"type": "boolean"}
            if description:
                out["description"] = description
            return out

        def s_array(item_schema: Dict[str, Any], description: Optional[str] = None) -> Dict[str, Any]:
            out: Dict[str, Any] = {"type": "array", "items": item_schema}
            if description:
                out["description"] = description
            return out

        def s_object(
            properties: Dict[str, Any],
            required: Optional[List[str]] = None,
            description: Optional[str] = None,
        ) -> Dict[str, Any]:
            out: Dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                out["required"] = required
            if description:
                out["description"] = description
            return out

        functions: List[Dict[str, Any]] = []

        functions.append(
            {
                "name": "get_twitter_profile",
                "description": "Fetch a Twitter profile by username (with or without @).",
                "parameters": s_object(
                    properties={"username": s_string("Twitter username")},
                    required=["username"],
                ),
            }
        )

        functions.append(
            {
                "name": "get_twitter_following",
                "description": "Fetch accounts the user follows (may be truncated).",
                "parameters": s_object(
                    properties={
                        "username": s_string("Twitter username"),
                        "oldest_first": s_boolean("Return oldest followings first"),
                    },
                    required=["username"],
                ),
            }
        )

        functions.append(
            {
                "name": "get_twitter_tweets",
                "description": "Fetch recent tweets for a user (count limited).",
                "parameters": s_object(
                    properties={
                        "username": s_string("Twitter username"),
                        "limit": s_integer("Number of tweets to fetch"),
                    },
                    required=["username"],
                ),
            }
        )

        functions.append(
            {
                "name": "bulk_get_twitter_profiles",
                "description": "Fetch up to 20 Twitter profiles in one request.",
                "parameters": s_object(
                    properties={
                        "identifiers": s_array(
                            s_string("Twitter username"),
                            description="List of up to 20 usernames",
                        )
                    },
                    required=["identifiers"],
                ),
            }
        )

        functions.append(
            {
                "name": "scrape_website",
                "description": "Scrape a URL using Firecrawl; returns text/markdown.",
                "parameters": s_object(
                    properties={"url": s_string("URL to scrape")},
                    required=["url"],
                ),
            }
        )

        return functions

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Dispatch to the Python tool implementations."""
        if not hasattr(self.tools_impl, name):
            return {"error": f"Unknown tool {name}"}
        fn = getattr(self.tools_impl, name)
        return fn(**args)

    # ------------------------------------------------------------------ #
    # Conversation loop
    # ------------------------------------------------------------------ #
    def _run_chat(self, user_query: str) -> tuple[str, Any, List[str]]:
        """Run a conversation with tool-calling using google-generativeai."""
        print(f"[DEBUG] _run_chat starting, query length={len(user_query)} chars")
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=self.system_prompt,
            tools=[{"function_declarations": self.function_specs}],
            generation_config={"response_mime_type": "text/plain"},
        )

        history: List[Dict[str, Any]] = [
            {"role": "user", "parts": [user_query]},
        ]
        tool_logs: List[str] = []

        start = time.time()
        print("[DEBUG] Calling initial generate_content with AUTO function calling...")
        response = model.generate_content(
            history,
            tool_config={"function_calling_config": {"mode": "AUTO"}},
        )
        print(f"[DEBUG] Initial generate_content completed in {time.time() - start:.1f}s")
        last_usage = getattr(response, "usage_metadata", None)

        while True:
            tool_calls = []
            for part in response.candidates[0].content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    tool_calls.append(fc)

            if not tool_calls:
                text = response.text or ""
                return text, last_usage, tool_logs

            for fc in tool_calls:
                name = fc.name or ""
                args = dict(fc.args or {})
                log_entry = f"[TOOL CALL] {name} args={json.dumps(args, ensure_ascii=False)}"
                print(log_entry)
                tool_logs.append(log_entry)

                result = self._call_tool(name, args)
                log_result = f"[TOOL RESULT] {name} result={json.dumps(result, ensure_ascii=False)[:2000]}"
                print(log_result)
                tool_logs.append(log_result)

                # Ensure tool result is always a dict for function_response.response
                if isinstance(result, dict):
                    response_payload = result
                else:
                    response_payload = {"value": result}

                # Append model function_call and tool response to history
                history.append(response.candidates[0].content)
                history.append(
                    {
                        "role": "tool",
                        "parts": [
                            {
                                "function_response": {
                                    "name": name,
                                    "response": response_payload,
                                }
                            }
                        ],
                    }
                )

            print(f"[DEBUG] Calling follow-up generate_content with history length={len(history)}")
            start = time.time()
            response = model.generate_content(
                history,
                tool_config={"function_calling_config": {"mode": "AUTO"}},
            )
            print(f"[DEBUG] Follow-up generate_content completed in {time.time() - start:.1f}s")
            last_usage = getattr(response, "usage_metadata", None)

    # ------------------------------------------------------------------ #
    # Public entrypoint
    # ------------------------------------------------------------------ #
    def run_research(self, twitter_handle: str, override_research: bool = False) -> Dict[str, Any]:
        """Run research for a single Twitter handle using the shared prompt."""
        if not twitter_handle:
            raise ValueError("twitter_handle is required")

        query = f"Research twitter profile {twitter_handle}"
        if override_research:
            query += (
                "\n\nIMPORTANT OVERRIDE: You must complete full research even if this"
                " is a later-stage project. Do NOT apply the early exit rule for"
                " late-stage projects. Provide complete analysis regardless of funding stage."
            )

        # Prefetch web context via Google Search tool (gemini-2.5-flash)
        search_context = self._run_google_search(query)
        if search_context:
            combined_query = f"{query}\n\nWEB_SEARCH_CONTEXT:\n{search_context}"
        else:
            combined_query = query

        text, usage, tool_logs = self._run_chat(combined_query)
        saved_path = self._save_markdown(twitter_handle, text)
        log_path = self._save_tool_log(saved_path, tool_logs)
        return {"text": text, "usage": usage, "saved_path": saved_path, "tool_log_path": log_path}

    def _save_markdown(self, twitter_handle: str, content: str) -> str:
        """Persist the final output to a markdown file under gemini_agent/logs/..."""
        handle = twitter_handle.replace("@", "")
        safe_handle = "".join(ch for ch in handle if ch.isalnum() or ch in ("_", "-")) or "unknown"
        date_str = datetime.now().strftime("%Y%m%d")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = Path(__file__).resolve().parent / "logs" / f"projects_{date_str}" / "gemini"
        base_dir.mkdir(parents=True, exist_ok=True)
        outfile = base_dir / f"{safe_handle}_{timestamp}.md"
        outfile.write_text(content, encoding="utf-8")
        return str(outfile)

    def _save_tool_log(self, saved_markdown_path: str, logs: List[str]) -> Optional[str]:
        """Write tool call logs to a sidecar .log file next to the markdown output."""
        if not saved_markdown_path:
            return None
        log_path = Path(saved_markdown_path).with_suffix(".log")
        log_path.write_text("\n".join(logs), encoding="utf-8")
        return str(log_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick Gemini research runner.")
    parser.add_argument("--twitter", required=True, help="Twitter handle (with or without @)")
    parser.add_argument("--override_research", action="store_true", help="Force full research even if late-stage")
    parser.add_argument("--prompt_path", help="Optional custom system prompt path")
    parser.add_argument("--model", default="gemini-3-pro-preview", help="Gemini model name to use")
    args = parser.parse_args()

    agent = GeminiResearchAgent(
        model=args.model,
        prompt_path=args.prompt_path,
    )
    result = agent.run_research(args.twitter, override_research=args.override_research)
    print("\n=== Final Output ===\n")
    print(result["text"])
    if result.get("usage"):
        print("\n=== Usage (from response.usage_metadata) ===")
        print(result["usage"])
    if result.get("saved_path"):
        print(f"\nSaved to: {result['saved_path']}")
    if result.get("tool_log_path"):
        print(f"Tool log: {result['tool_log_path']}")


if __name__ == "__main__":
    main()
