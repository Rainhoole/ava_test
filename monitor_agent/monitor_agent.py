#!/usr/bin/env python3
"""Monitor Agent

Monitors previously researched projects flagged for monitoring in Notion.

Design goals:
- Only process pages whose `Research Status` contains/equals `monitor`.
- Sort worklist by `Research Date` ascending (oldest checked first).
- Use prior context (Monitor Pack + prior report metadata) to cheaply decide whether
  to keep monitoring vs. escalate to full deep research.
- When escalation is needed, reuse the existing streaming deep-research pipeline
  (StreamingProcessor + NotionUpdater) so reports remain consistent.

This is an initial scaffold intended to match the architecture of:
- `research_agent/research_agent.py`
- `research_agent/streaming_processor.py`
- `research_agent/notion_updater.py`

See `monitor_agent/design.md` for the full end-to-end design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from notion_client import Client


# -----------------------------
# Path setup (repo-relative imports)
# -----------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESEARCH_AGENT_DIR = os.path.join(REPO_ROOT, "research_agent")
MCP_SERVER_DIR = os.path.join(REPO_ROOT, "mcp_server")

# Allow importing non-packaged modules from sibling folders
sys.path.insert(0, RESEARCH_AGENT_DIR)
sys.path.insert(0, MCP_SERVER_DIR)

# Reuse existing components
from notion_updater import NotionUpdater  # type: ignore
from streaming_processor import StreamingProcessor  # type: ignore
from tools import Tools  # type: ignore


logger = logging.getLogger(__name__)


# -----------------------------
# Config / helpers
# -----------------------------

def _setup_logging() -> str:
    """Create a per-run console log under logs/monitor_YYYYMMDD."""
    log_root = os.path.join(REPO_ROOT, "logs")
    os.makedirs(log_root, exist_ok=True)

    daily = datetime.now().strftime("%Y%m%d")
    session_dir = os.path.join(log_root, f"monitor_{daily}")
    os.makedirs(session_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = os.path.join(session_dir, f"console_output_{ts}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(logfile, mode="w", encoding="utf-8"), logging.StreamHandler()],
    )
    return logfile


def _get_text_property(prop: Dict[str, Any]) -> str:
    """Extract text from a Notion title/rich_text property."""
    if not prop:
        return ""
    if prop.get("title"):
        return "".join([t.get("plain_text", "") for t in prop["title"]])
    if prop.get("rich_text"):
        return "".join([t.get("plain_text", "") for t in prop["rich_text"]])
    return ""


def _get_multi_select(prop: Dict[str, Any]) -> List[str]:
    items = prop.get("multi_select") or []
    if not isinstance(items, list):
        return []
    return [str(i.get("name", "")).strip() for i in items if isinstance(i, dict) and i.get("name")]


def _parse_date(prop: Dict[str, Any]) -> Optional[str]:
    date_obj = (prop.get("date") or {}) if isinstance(prop, dict) else {}
    start = date_obj.get("start")
    return start


def _normalize_handle(raw: str) -> str:
    raw = (raw or "").strip()
    raw = re.sub(r"https?://[^\s]+", "", raw).strip()
    raw = raw.replace("@", "").strip()
    return raw


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def extract_meta_monitor(report_markdown: str) -> Optional[bool]:
    """Extract META_MONITOR: Yes/No from a report."""
    if not report_markdown:
        return None
    m = re.search(r"^META_MONITOR:\s*(Yes|No)\b", report_markdown, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().lower() == "yes"


def strip_monitor_pack(report_markdown: str) -> Tuple[str, Optional[str]]:
    """Remove the AVA monitor pack sentinel block if present.

    Returns:
        (clean_markdown, monitor_pack_json_str_or_none)
    """
    if not report_markdown:
        return report_markdown, None

    start = report_markdown.find("<<<AVA_MONITOR_PACK_V1>>>")
    end = report_markdown.find("<<<END_AVA_MONITOR_PACK_V1>>>")
    if start == -1 or end == -1 or end < start:
        return report_markdown, None

    end_idx = end + len("<<<END_AVA_MONITOR_PACK_V1>>>")
    pack_block = report_markdown[start:end_idx]

    # Extract JSON content inside markers
    json_part = pack_block
    json_part = json_part.replace("<<<AVA_MONITOR_PACK_V1>>>", "").replace("<<<END_AVA_MONITOR_PACK_V1>>>", "")
    json_part = json_part.strip()

    clean = (report_markdown[:start] + report_markdown[end_idx:]).strip() + "\n"
    return clean, json_part


def compute_snapshot_fingerprint(profile: Dict[str, Any], tweets: Dict[str, Any]) -> str:
    """Compute a cheap fingerprint for change detection (heuristic)."""
    website = (profile.get("website") or "").strip()
    bio = (profile.get("bio") or "").strip()

    tweet_entries = tweets.get("entries") or tweets.get("tweets") or []
    if not isinstance(tweet_entries, list):
        tweet_entries = []

    texts: List[str] = []
    urls: List[str] = []
    for t in tweet_entries[:20]:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or "").strip()
        if text:
            texts.append(text)
        for u in (t.get("urls") or []):
            if isinstance(u, str) and u:
                urls.append(u)

    # Normalize inputs to be stable-ish
    blob = json.dumps(
        {
            "website": website.lower(),
            "bio": re.sub(r"\s+", " ", bio).strip().lower(),
            "tweet_text": "\n".join(texts).lower(),
            "tweet_urls": sorted(set(u.lower().rstrip("/") for u in urls)),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class MonitorProject:
    page_id: str
    name: str
    twitter_handle: str
    research_status: List[str]
    research_date: Optional[str]
    monitor_pack_raw: str


class MonitorAgent:
    def __init__(self, model: str, triage_model: str, use_flex: bool = True, mcp_server_url: Optional[str] = None):
        self.notion = Client(auth=os.environ.get("NOTION_API_KEY"))
        self.database_id = os.environ.get("NOTION_DATABASE_ID")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID is required")

        self.model = model
        self.triage_model = triage_model
        self.use_flex = use_flex
        self.mcp_server_url = mcp_server_url or os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")

        # Reuse Notion updater for full report uploads
        self.notion_updater = NotionUpdater(self.notion, self.database_id)

        # Direct (non-LLM) tool access for cheap snapshot pulls
        self.tools = Tools()

        # Logs folder matching research_agent style
        log_root = os.path.join(REPO_ROOT, "logs")
        os.makedirs(log_root, exist_ok=True)
        daily = datetime.now().strftime("%Y%m%d")
        self.session_dir = os.path.join(log_root, f"monitor_projects_{daily}")
        os.makedirs(self.session_dir, exist_ok=True)

    def get_projects_to_monitor(self, limit: int) -> List[MonitorProject]:
        """Query Notion for pages with Research Status ==/contains 'monitor', sorted by Research Date asc."""
        response = self.notion.databases.query(
            database_id=self.database_id,
            filter={
                "and": [
                    {"property": "Research Status", "multi_select": {"contains": "monitor"}},
                    # Optional: avoid double-processing if you add a 'monitoring' lock
                    # {"property": "Research Status", "multi_select": {"does_not_contain": "monitoring"}},
                ]
            },
            sorts=[
                {"property": "Research Date", "direction": "ascending"},
                {"timestamp": "created_time", "direction": "ascending"},
            ],
            page_size=max(limit * 2, limit),
        )

        results = response.get("results", [])
        projects: List[MonitorProject] = []

        for page in results:
            props = page.get("properties", {}) or {}
            name = _get_text_property(props.get("Name", {}))
            twitter = _normalize_handle(_get_text_property(props.get("Twitter", {})))
            if not twitter:
                continue

            status = _get_multi_select(props.get("Research Status", {}))
            research_date = _parse_date(props.get("Research Date", {}))
            monitor_pack_raw = _get_text_property(props.get("Monitor Pack", {}))

            projects.append(
                MonitorProject(
                    page_id=page["id"],
                    name=name,
                    twitter_handle=twitter,
                    research_status=status,
                    research_date=research_date,
                    monitor_pack_raw=monitor_pack_raw,
                )
            )

            if len(projects) >= limit:
                break

        return projects

    def update_research_status(self, page_id: str, status: str):
        """Set Research Status to a single tag. Adjust if you adopt multi-tag semantics."""
        self.notion.pages.update(
            page_id=page_id,
            properties={"Research Status": {"multi_select": [{"name": status}]}},
        )

    def update_monitor_fields(self, page_id: str, *, monitor_pack: Optional[str] = None, last_check: bool = True, verdict: Optional[str] = None):
        properties: Dict[str, Any] = {}
        if monitor_pack is not None:
            properties["Monitor Pack"] = {"rich_text": [{"type": "text", "text": {"content": monitor_pack[:1900]}}]}
        if last_check:
            properties["Last Monitor Check"] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
        if verdict is not None:
            properties["Monitor Verdict"] = {"select": {"name": verdict}}

        if properties:
            self.notion.pages.update(page_id=page_id, properties=properties)

    # -----------------------------
    # Monitoring flow
    # -----------------------------

    def fetch_current_snapshot(self, twitter_handle: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        profile = self.tools.get_twitter_profile(twitter_handle)
        tweets = self.tools.get_twitter_tweets(twitter_handle, limit=20)
        return profile, tweets

    def decide_escalation(
        self,
        *,
        baseline_pack: Optional[Dict[str, Any]],
        current_profile: Dict[str, Any],
        current_tweets: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Cheap heuristic decision (placeholder).

        TODO: Add full diff rules + optional LLM triage call using `monitor_agent_triage_prompt.md`.
        """
        baseline_fingerprint = (baseline_pack or {}).get("baseline_fingerprint") if isinstance(baseline_pack, dict) else None
        current_fingerprint = compute_snapshot_fingerprint(current_profile, current_tweets)

        if baseline_fingerprint and isinstance(baseline_fingerprint, str) and baseline_fingerprint == current_fingerprint:
            return {"recommended_action": "continue_monitoring", "verdict": "no_change", "confidence": "high"}

        # Conservative default: if we can't prove no-change, escalate via triage LLM (not implemented here)
        return {"recommended_action": "run_deep_research", "verdict": "material_change", "confidence": "low"}

    def run_deep_research(self, project: MonitorProject, system_prompt_path: str) -> Optional[str]:
        system_message = open(system_prompt_path, "r", encoding="utf-8").read()

        processor = StreamingProcessor(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=self.model,
            use_flex=self.use_flex,
            session_dir=self.session_dir,
            twitter_handle=project.twitter_handle,
            project_name=project.name,
            worker_id="monitor",
            position=1,
            total=1,
            mock_mode=False,
        )

        user_query = f"Monitor and update research for twitter profile {project.twitter_handle}."

        return processor.process_research(
            system_message=system_message,
            user_query=user_query,
            mcp_server_url=self.mcp_server_url,
            max_retries=3 if self.use_flex else 1,
        )

    def process_project(self, project: MonitorProject, *, deep_prompt_path: str):
        logger.info(f"[monitor] Starting: {project.name} (@{project.twitter_handle})")

        # Lock
        try:
            self.update_research_status(project.page_id, "monitoring")
        except Exception as exc:
            logger.error(f"Failed to set monitoring status for {project.name}: {exc}")
            return

        baseline_pack = _safe_json_loads(project.monitor_pack_raw) if project.monitor_pack_raw else None

        # Snapshot
        profile, tweets = self.fetch_current_snapshot(project.twitter_handle)

        # Decide
        decision = self.decide_escalation(baseline_pack=baseline_pack, current_profile=profile, current_tweets=tweets)
        action = decision.get("recommended_action")

        if action == "continue_monitoring":
            logger.info(f"[monitor] No meaningful change: {project.name} (@{project.twitter_handle})")
            self.update_monitor_fields(project.page_id, last_check=True, verdict=decision.get("verdict"))
            self.update_research_status(project.page_id, "monitor")
            return

        # Deep research
        report = self.run_deep_research(project, deep_prompt_path)
        if not report:
            logger.error(f"[monitor] Deep research failed for {project.name}")
            self.update_research_status(project.page_id, "monitor")
            return

        # Extract monitor pack (if any) and remove from report body
        clean_report, monitor_pack_str = strip_monitor_pack(report)

        # Upload full report
        try:
            project_dir = os.path.join(self.session_dir, re.sub(r"[^\w]", "", project.twitter_handle))
            url = self.notion_updater.update_item_with_research(project.page_id, project.name, clean_report, project_dir)
            logger.info(f"[monitor] Uploaded report: {url}")
        except Exception as exc:
            logger.error(f"[monitor] Upload failed for {project.name}: {exc}")

        # Decide whether to keep monitoring based on META_MONITOR
        meta_monitor = extract_meta_monitor(report)
        if meta_monitor is True:
            logger.info(f"[monitor] META_MONITOR=Yes → keeping status as monitor")
            if monitor_pack_str:
                self.update_monitor_fields(project.page_id, monitor_pack=monitor_pack_str, last_check=True)
            self.update_research_status(project.page_id, "monitor")
        elif meta_monitor is False:
            logger.info(f"[monitor] META_MONITOR=No → clearing monitor flag")
            if monitor_pack_str:
                self.update_monitor_fields(project.page_id, monitor_pack=monitor_pack_str, last_check=True)
            self.update_research_status(project.page_id, "completed")
        else:
            logger.warning(f"[monitor] META_MONITOR missing → defaulting to monitor")
            if monitor_pack_str:
                self.update_monitor_fields(project.page_id, monitor_pack=monitor_pack_str, last_check=True)
            self.update_research_status(project.page_id, "monitor")


def main() -> None:
    logfile = _setup_logging()
    logger.info(f"Monitor Agent starting (log: {logfile})")

    # Load env from repo root
    load_dotenv(os.path.join(REPO_ROOT, ".env"))

    parser = argparse.ArgumentParser(description="Monitor Agent for Notion projects")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--instant", action="store_true", help="Disable flex (faster, more expensive)")
    parser.add_argument("--model", type=str, default=os.environ.get("OPENAI_MODEL") or "o3")
    parser.add_argument("--triage-model", type=str, default="o4-mini")
    parser.add_argument(
        "--prompt",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "monitor_agent_prompt_al.md"),
        help="System prompt for deep monitoring research",
    )

    args = parser.parse_args()

    required = ["OPENAI_API_KEY", "NOTION_API_KEY", "NOTION_DATABASE_ID"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

    agent = MonitorAgent(model=args.model, triage_model=args.triage_model, use_flex=not args.instant)

    projects = agent.get_projects_to_monitor(args.batch_size)
    logger.info(f"Found {len(projects)} projects to monitor")

    for p in projects:
        agent.process_project(p, deep_prompt_path=args.prompt)


if __name__ == "__main__":
    main()
