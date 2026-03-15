"""Backfill category scores in Notion based on structured AI reports.

Implements the plan documented in docs/notion_scores_backfill.md:
  * Queries pages created after a cutoff (default 2025-06-01) using env vars.
  * Flattens report blocks, supports multiple reports per page, and extracts
    Founder Pattern, Idea Pattern, Structural Advantage, Asymmetric Signal.
  * Uses structured regex heuristics first, optional GPT fallback second.
  * Chooses the highest score across reports without normalising stored values.
  * Supports dry runs, CSV audit output, and mirrors updates to an external DB.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from dotenv import load_dotenv
from notion_client import Client

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None


logger = logging.getLogger(__name__)


DEFAULT_CREATED_AFTER = "2025-06-01T00:00:00Z"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = SCRIPT_DIR / "notion_scores_backfill_audit.csv"


CATEGORY_CONFIG = {
    "founder_pattern": {
        "property": "Founder Pattern",
        "synonyms": ["Founder Pattern"],
    },
    "idea_pattern": {
        "property": "Idea Pattern",
        "synonyms": ["Idea Pattern"],
    },
    "structural_advantage": {
        "property": "Structural Advantage",
        "synonyms": ["Structural Advantage"],
    },
    "asymmetric_signal": {
        "property": "Asymmetric Signal",
        "synonyms": ["Asymmetric Signal", "Asymmetric Signals"],
    },
}


FRACTION_RE = re.compile(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
PLAIN_RE = re.compile(
    r"(?:score|rating|value)\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
NUMERIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class NotionConfig:
    api_key: str
    database_id: str
    external_database_id: Optional[str]


@dataclass
class ScoreCandidate:
    category: str
    raw: str
    match_excerpt: str
    method: str
    report_index: int
    ratio: Optional[float]


@dataclass
class PageAudit:
    page_id: str
    title: str
    values: Dict[str, Optional[str]]
    numeric_values: Dict[str, Optional[float]]
    methods: Dict[str, str]
    notes: List[str] = field(default_factory=list)


def load_config() -> NotionConfig:
    load_dotenv()

    api_key = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DATABASE_ID")
    external_database_id = os.getenv("NOTION_DATABASE_ID_EXT")

    missing = [name for name, value in (
        ("NOTION_API_KEY", api_key),
        ("NOTION_DATABASE_ID", database_id),
    ) if not value]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return NotionConfig(
        api_key=api_key,
        database_id=database_id,
        external_database_id=external_database_id or None,
    )


def iter_database_pages(
    client: Client,
    database_id: str,
    created_after: str,
    page_size: int,
    max_items: Optional[int] = None,
    use_edited_time: bool = False,
    start_cursor: Optional[str] = None,
) -> Iterator[dict]:
    """Yield pages from Notion with pagination."""

    timestamp_field = "last_edited_time" if use_edited_time else "created_time"
    payload = {
        "filter": {
            "timestamp": timestamp_field,
            timestamp_field: {"after": created_after},
        },
        "page_size": page_size,
        "sorts": [
            {
                "timestamp": timestamp_field,
                "direction": "descending",
            }
        ],
    }

    yielded = 0
    cursor = start_cursor

    while True:
        if cursor:
            payload["start_cursor"] = cursor
        elif "start_cursor" in payload:
            payload.pop("start_cursor")

        response = client.databases.query(database_id=database_id, **payload)
        results: List[dict] = response.get("results", [])

        for page in results:
            if max_items is not None and yielded >= max_items:
                logger.debug("Reached max_items=%s; stopping iteration", max_items)
                return
            yielded += 1
            yield page

        if not response.get("has_more"):
            break

        cursor = response.get("next_cursor")
        if cursor is None:
            break


def get_title(page: dict) -> str:
    properties = page.get("properties", {})
    priority_props: Iterable[str] = ("Name", "Title", "Project", "Project Name")

    for prop in priority_props:
        if prop in properties and properties[prop]["type"] == "title":
            title_content = properties[prop]["title"]
            if title_content:
                return title_content[0].get("plain_text", "Untitled")

    for value in properties.values():
        if value.get("type") == "title" and value.get("title"):
            return value["title"][0].get("plain_text", "Untitled")

    return "Untitled"


def gather_text_from_block(block: dict) -> str:
    block_type = block.get("type")
    data = block.get(block_type, {}) if block_type else {}

    fragments = []
    for fragment in data.get("rich_text", []):
        text = fragment.get("plain_text")
        if text:
            fragments.append(text)

    if not fragments:
        return ""

    text_content = "".join(fragments)

    if block_type in {"heading_1", "heading_2", "heading_3"}:
        return f"# {text_content}"
    if block_type in {"bulleted_list_item", "numbered_list_item"}:
        return f"- {text_content}"
    if block_type == "to_do":
        checkbox = "[x]" if data.get("checked") else "[ ]"
        return f"{checkbox} {text_content}"
    if block_type == "callout":
        icon = data.get("icon", {}).get("emoji", "")
        emoji_prefix = f"{icon} " if icon else ""
        return f"{emoji_prefix}{text_content}"

    return text_content


def fetch_block_children(client: Client, block_id: str) -> List[dict]:
    children: List[dict] = []
    cursor: Optional[str] = None

    while True:
        response = client.blocks.children.list(block_id=block_id, start_cursor=cursor)
        children.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return children


def flatten_page_content(
    client: Client,
    page_id: str,
    max_blocks: Optional[int] = None,
) -> List[str]:
    content_lines: List[str] = []
    processed = 0

    def walk_blocks(blocks: List[dict]) -> None:
        nonlocal processed
        for block in blocks:
            if max_blocks is not None and processed >= max_blocks:
                return

            text = gather_text_from_block(block)
            if text:
                content_lines.append(text)
            processed += 1

            if block.get("has_children"):
                children = fetch_block_children(client, block["id"])
                walk_blocks(children)
                if max_blocks is not None and processed >= max_blocks:
                    return

    top_level = fetch_block_children(client, page_id)
    walk_blocks(top_level)

    return content_lines


def collect_existing_numeric(properties: Dict) -> Dict[str, Optional[float]]:
    numeric_values: Dict[str, Optional[float]] = {}
    for key, cfg in CATEGORY_CONFIG.items():
        prop = properties.get(cfg["property"])
        if prop and prop.get("type") == "number":
            numeric_values[key] = prop.get("number")
        else:
            numeric_values[key] = None
    return numeric_values


def split_reports(content_lines: List[str]) -> List[str]:
    sentinels = ("ava's report", "generated by ava's research agent", "=== report start ===")
    reports: List[List[str]] = []
    current: List[str] = []
    started = False

    for line in content_lines:
        normalized = line.strip().lower()
        if any(marker in normalized for marker in sentinels):
            if current:
                reports.append(current)
                current = []
            started = True
        if started:
            current.append(line)

    if current:
        reports.append(current)

    if not reports:
        text = "\n".join(content_lines).strip()
        return [text] if text else []

    return ["\n".join(report).strip() for report in reports if report]


def extract_scoring_section(report_text: str) -> Optional[str]:
    lines = report_text.splitlines()
    start_idx: Optional[int] = None

    for idx, line in enumerate(lines):
        if "scoring assessment" in line.lower():
            start_idx = idx
            break

    if start_idx is None:
        return None

    collected: List[str] = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        lower = stripped.lower()
        if collected and (
            (stripped.startswith("#") and "scoring" not in lower)
            or stripped.startswith("=== SECTION")
        ):
            break
        collected.append(line)

    return "\n".join(collected).strip() if collected else None


def contains_synonym(text: str, synonyms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(syn.lower() in lowered for syn in synonyms)


def clean_fraction(raw: str) -> Tuple[Optional[float], Optional[float]]:
    numbers = [float(token) for token in NUMERIC_TOKEN_RE.findall(raw)]
    if len(numbers) != 2:
        return None, None
    numerator, denominator = numbers
    if denominator <= 0:
        return None, None
    if denominator <= 4:
        return None, None
    return numerator, denominator


def compute_ratio(raw: str) -> Optional[float]:
    stripped = raw.strip()

    if FRACTION_RE.fullmatch(stripped.replace(" ", "")) or "/" in stripped:
        numerator, denominator = clean_fraction(stripped)
        if numerator is None or denominator is None:
            return None
        return max(0.0, min(1.0, numerator / denominator))

    if PERCENT_RE.fullmatch(stripped.replace(" ", "")) or stripped.endswith("%"):
        try:
            value = float(stripped.rstrip("% "))
        except ValueError:
            return None
        return max(0.0, min(1.0, value / 100))

    plain_match = PLAIN_RE.search(stripped)
    if plain_match:
        try:
            value = float(plain_match.group(1))
        except (ValueError, TypeError):
            return None
        if value <= 10:
            return max(0.0, min(1.0, value / 10))
        return None

    return None


def convert_raw_to_number(raw: str) -> Optional[float]:
    stripped = raw.strip()

    if "/" in stripped:
        numbers = [float(token) for token in NUMERIC_TOKEN_RE.findall(stripped)]
        if len(numbers) != 2:
            return None
        numerator, denominator = numbers
        if denominator <= 0:
            return None
        return numerator

    if stripped.endswith("%"):
        try:
            return float(stripped.rstrip("% "))
        except ValueError:
            return None

    return None


def find_score_in_line(line: str) -> Optional[str]:
    for match in FRACTION_RE.finditer(line):
        numerator, denominator = clean_fraction(match.group(0))
        if numerator is not None:
            return match.group(0).strip()

    for match in PERCENT_RE.finditer(line):
        return match.group(0).strip()

    match = PLAIN_RE.search(line)
    if match:
        raw = match.group(1).strip()
        return raw

    return None


def extract_candidates_from_text(
    text: str,
    category_key: str,
    synonyms: Iterable[str],
    method: str,
    report_index: int,
) -> List[ScoreCandidate]:
    candidates: List[ScoreCandidate] = []
    lines = text.splitlines()

    for line in lines:
        if not contains_synonym(line, synonyms):
            continue

        raw = find_score_in_line(line)
        if not raw:
            continue

        if "/" in raw and re.search(r"/\s*4\b", raw):
            continue

        ratio = compute_ratio(raw)
        candidates.append(
            ScoreCandidate(
                category=category_key,
                raw=raw,
                match_excerpt=line.strip(),
                method=method,
                report_index=report_index,
                ratio=ratio,
            )
        )

    return candidates


def extract_with_regex(report_text: str, report_index: int) -> List[ScoreCandidate]:
    candidates: List[ScoreCandidate] = []
    scoring_text = extract_scoring_section(report_text)

    if scoring_text:
        for key, cfg in CATEGORY_CONFIG.items():
            candidates.extend(
                extract_candidates_from_text(
                    scoring_text,
                    category_key=key,
                    synonyms=cfg["synonyms"],
                    method="regex_structured",
                    report_index=report_index,
                )
            )

    for key, cfg in CATEGORY_CONFIG.items():
        existing = {c.match_excerpt for c in candidates if c.category == key}
        more = extract_candidates_from_text(
            report_text,
            category_key=key,
            synonyms=cfg["synonyms"],
            method="regex_global",
            report_index=report_index,
        )
        for candidate in more:
            if candidate.match_excerpt not in existing:
                candidates.append(candidate)

    return candidates


def parse_llm_json(response_text: str) -> Dict[str, Dict[str, Optional[str]]]:
    try:
        data = json.loads(response_text)
        if not isinstance(data, dict):
            raise ValueError("LLM response is not a JSON object")
        return data
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from LLM: {exc}") from exc


def llm_extract_scores(
    report_text: str,
    model: str,
    client: OpenAI,
) -> Dict[str, ScoreCandidate]:
    system_prompt = (
        "Extract the explicit numeric scores for these categories: Founder Pattern, Idea Pattern, "
        "Structural Advantage, Asymmetric Signal. Return JSON with keys founder_pattern, "
        "idea_pattern, structural_advantage, asymmetric_signal. Each value must be an object with "
        "fields raw (string or null) and matched (string or null). Only copy numbers that appear in "
        "the text verbatim. If a category has no explicit number, set both fields to null."
    )
    user_prompt = (
        "Report text:\n" + report_text + "\n\nRemember: only extract numbers exactly present in the text."
    )

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("LLM extraction failed: %s", exc)
        return {}

    response_text = getattr(response, "output_text", "") or ""
    if not response_text:
        segments: List[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = content.get("text") if isinstance(content, dict) else None
                if text:
                    segments.append(text)
        response_text = "".join(segments)

    try:
        parsed = parse_llm_json(response_text)
    except ValueError as exc:
        logger.warning("Failed to parse LLM JSON: %s", exc)
        return {}

    matches: Dict[str, ScoreCandidate] = {}

    for key in CATEGORY_CONFIG.keys():
        entry = parsed.get(key)
        if not isinstance(entry, dict):
            continue
        raw = entry.get("raw")
        matched = entry.get("matched") or entry.get("match")
        if not raw or not matched:
            continue
        if raw not in report_text and (matched not in report_text):
            continue
        if "/" in raw and re.search(r"/\s*4\b", raw):
            continue
        ratio = compute_ratio(raw)
        matches[key] = ScoreCandidate(
            category=key,
            raw=raw.strip(),
            match_excerpt=matched.strip(),
            method="llm_fallback",
            report_index=math.inf,
            ratio=ratio,
        )

    return matches


def choose_best_candidates(candidates: List[ScoreCandidate]) -> Dict[str, ScoreCandidate]:
    best: Dict[str, ScoreCandidate] = {}

    for candidate in candidates:
        current = best.get(candidate.category)
        if not current:
            best[candidate.category] = candidate
            continue

        if candidate.ratio is not None and current.ratio is None:
            best[candidate.category] = candidate
            continue
        if candidate.ratio is None and current.ratio is not None:
            continue
        if candidate.ratio is not None and current.ratio is not None:
            if candidate.ratio > current.ratio:
                best[candidate.category] = candidate
                continue
            if candidate.ratio < current.ratio:
                continue

        if candidate.report_index > current.report_index:
            best[candidate.category] = candidate
        elif candidate.report_index == current.report_index:
            best[candidate.category] = candidate

    return best


def get_property_value(prop: dict) -> Optional[float]:
    prop_type = prop.get("type")
    if prop_type == "number":
        return prop.get("number")
    if prop_type == "rich_text":
        fragments = prop.get("rich_text", [])
        text = "".join(fragment.get("plain_text", "") for fragment in fragments).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def find_external_page_id(client: Client, database_id: str, title: str) -> Optional[str]:
    title_props = ["Name", "Title", "Project", "Project Name"]

    for prop in title_props:
        try:
            response = client.databases.query(
                database_id=database_id,
                filter={
                    "property": prop,
                    "title": {"equals": title},
                },
                page_size=1,
            )
        except Exception as exc:  # pragma: no cover - Notion API edge
            logger.debug("External query failed for property %s: %s", prop, exc)
            continue

        results = response.get("results", [])
        if results:
            return results[0]["id"]

    return None


def update_page_properties(
    client: Client,
    page_id: str,
    updates: Dict[str, Dict],
) -> None:
    if not updates:
        return
    client.pages.update(page_id=page_id, properties=updates)


def build_audit_record(
    page_id: str,
    title: str,
    best: Dict[str, ScoreCandidate],
    numeric_values: Dict[str, Optional[float]],
    notes: List[str],
) -> PageAudit:
    values: Dict[str, Optional[str]] = {}
    methods: Dict[str, str] = {}

    for key in CATEGORY_CONFIG.keys():
        candidate = best.get(key)
        values[key] = candidate.raw if candidate else None
        methods[key] = candidate.method if candidate else ""

    numeric_map = {key: numeric_values.get(key) for key in CATEGORY_CONFIG.keys()}

    return PageAudit(
        page_id=page_id,
        title=title,
        values=values,
        numeric_values=numeric_map,
        methods=methods,
        notes=notes,
    )


def write_audit_csv(records: List[PageAudit], csv_path: Optional[str]) -> None:
    if not csv_path:
        return

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "page_id",
        "title",
        "founder_pattern",
        "founder_pattern_numeric",
        "idea_pattern",
        "idea_pattern_numeric",
        "structural_advantage",
        "structural_advantage_numeric",
        "asymmetric_signal",
        "asymmetric_signal_numeric",
        "methods",
        "notes",
    ]

    write_header = not path.exists()
    try:
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for record in records:
                writer.writerow({
                    "page_id": record.page_id,
                    "title": record.title,
                    "founder_pattern": record.values.get("founder_pattern"),
                    "founder_pattern_numeric": record.numeric_values.get("founder_pattern"),
                    "idea_pattern": record.values.get("idea_pattern"),
                    "idea_pattern_numeric": record.numeric_values.get("idea_pattern"),
                    "structural_advantage": record.values.get("structural_advantage"),
                    "structural_advantage_numeric": record.numeric_values.get("structural_advantage"),
                    "asymmetric_signal": record.values.get("asymmetric_signal"),
                    "asymmetric_signal_numeric": record.numeric_values.get("asymmetric_signal"),
                    "methods": "; ".join(
                        f"{key}:{value}" for key, value in record.methods.items() if value
                    ),
                    "notes": " | ".join(record.notes),
                })
    except PermissionError as exc:  # pragma: no cover - filesystem permissions
        logger.error("Failed to write audit CSV to %s: %s", path, exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Notion score properties from AI-generated reports.",
    )
    parser.add_argument("--created-after", default=DEFAULT_CREATED_AFTER, help="ISO timestamp filter.")
    parser.add_argument("--use-edited-time", action="store_true", help="Filter/sort by last_edited_time instead of created_time.")
    parser.add_argument("--page-size", type=int, default=50, help="Notion query page size (max 100).")
    parser.add_argument("--max-items", type=int, default=5, help="Maximum pages to process.")
    parser.add_argument("--start-cursor", default=None, help="Optional Notion cursor to resume pagination.")
    parser.add_argument("--max-blocks", type=int, default=None, help="Limit blocks per page (debug).")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing to Notion.")
    parser.add_argument("--no-llm", action="store_true", help="Disable GPT fallback extraction.")
    parser.add_argument("--llm-model", default="gpt-5-nano", help="Model to use for fallback extraction.")
    parser.add_argument("--max-workers", type=int, default=10, help="Concurrent page-processing workers (default 10).")
    parser.add_argument("--max-retries", type=int, default=1, help="Retry attempts per page on recoverable failures (default 1).")
    parser.add_argument(
        "--csv-path",
        default=str(DEFAULT_CSV_PATH),
        help="Path to write audit CSV (default is scripts/notion_scores_backfill_audit.csv).",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging verbosity.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    try:
        config = load_config()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise

    client = Client(auth=config.api_key)
    use_llm = not args.no_llm
    llm_client = None
    if use_llm:
        if OpenAI is None:
            raise RuntimeError("openai package not available but GPT fallback requested")
        llm_client = OpenAI()

    audit_records: List[PageAudit] = []

    pages_iter = iter_database_pages(
        client=client,
        database_id=config.database_id,
        created_after=args.created_after,
        page_size=max(1, min(args.page_size, 100)),
        max_items=None,
        use_edited_time=args.use_edited_time,
        start_cursor=args.start_cursor,
    )

    max_workers = max(1, args.max_workers)
    max_retries = max(0, args.max_retries)

    def apply_failure_updates(
        client: Client,
        config: NotionConfig,
        page_id: str,
        title: str,
        properties: Dict,
        failure_values: Dict[str, float],
    ) -> None:
        updates: Dict[str, Dict] = {}
        for key, cfg in CATEGORY_CONFIG.items():
            property_name = cfg["property"]
            prop = properties.get(property_name)
            if prop and prop.get("type") == "number":
                updates[property_name] = {"number": failure_values.get(key, -1.0)}
        if not updates:
            return
        update_page_properties(client, page_id, updates)
        if config.external_database_id:
            external_page_id = find_external_page_id(client, config.external_database_id, title)
            if external_page_id:
                try:
                    update_page_properties(client, external_page_id, updates)
                except Exception as exc:  # pragma: no cover - Notion failure
                    logger.warning("Failed to update external page %s for %s: %s", external_page_id, title, exc)

    def process_page(page: dict, attempt: int = 1) -> Tuple[PageAudit, bool]:
        page_id = page.get("id")
        title = get_title(page)
        logger.info("Processing page %s (%s)", title, page_id)

        properties = page.get("properties", {})
        existing_numeric = collect_existing_numeric(properties)
        notes: List[str] = []
        start_time = time.perf_counter()

        # Skip if all four properties already have numeric values
        if all(existing_numeric.get(key) is not None for key in CATEGORY_CONFIG.keys()):
            notes.append("skipped_already_filled")
            elapsed = time.perf_counter() - start_time
            logger.info("Skipping %s (already filled) in %.2fs", title, elapsed)
            return build_audit_record(page_id, title, {}, existing_numeric, notes), False

        try:
            lines = flatten_page_content(client, page_id, max_blocks=args.max_blocks)
        except Exception as exc:  # pragma: no cover - API errors
            if attempt <= max_retries:
                logger.warning(
                    "Failed to fetch blocks for %s (attempt %d/%d): %s - retrying",
                    page_id,
                    attempt,
                    max_retries,
                    exc,
                )
                return process_page(page, attempt + 1)
            logger.warning("Failed to fetch blocks for %s: %s", page_id, exc)
            failure_values = {key: -1.0 for key in CATEGORY_CONFIG.keys()}
            if not args.dry_run:
                apply_failure_updates(client, config, page_id, title, properties, failure_values)
            elapsed = time.perf_counter() - start_time
            logger.info("Timing %s - fetch failed after %.2fs", title, elapsed)
            return build_audit_record(page_id, title, {}, failure_values, [f"block_fetch_error:{exc}"]), True

        fetch_done = time.perf_counter()

        reports = split_reports(lines)
        if not reports:
            failure_values = {key: -1.0 for key in CATEGORY_CONFIG.keys()}
            notes.append("no_report_content")
            if not args.dry_run:
                apply_failure_updates(client, config, page_id, title, properties, failure_values)
            elapsed = time.perf_counter() - start_time
            logger.info(
                "Timing %s - fetch %.2fs, parse %.2fs, update %.2fs",
                title,
                fetch_done - start_time,
                0.0,
                elapsed - fetch_done,
            )
            return build_audit_record(page_id, title, {}, failure_values, notes), True

        all_candidates: List[ScoreCandidate] = []

        for idx, report in enumerate(reports):
            candidates = extract_with_regex(report, idx)
            all_candidates.extend(candidates)

            regex_categories = {c.category for c in candidates}
            if use_llm and len(regex_categories) < 3:
                llm_matches = llm_extract_scores(report, args.llm_model, llm_client) if llm_client else {}
                for key, candidate in llm_matches.items():
                    if not candidate.raw:
                        continue
                    candidate.report_index = idx
                    all_candidates.append(candidate)

        extract_done = time.perf_counter()
        best = choose_best_candidates(all_candidates)
        numeric_values: Dict[str, Optional[float]] = {}

        for key in CATEGORY_CONFIG.keys():
            candidate = best.get(key)
            numeric_value = convert_raw_to_number(candidate.raw) if candidate else None
            if numeric_value is None:
                numeric_values[key] = -1.0
                notes.append(f"assigned_failure:{key}")
            else:
                numeric_values[key] = numeric_value
            if candidate:
                logger.debug(
                    "Best candidate for %s: raw=%s numeric=%s method=%s ratio=%s",
                    key,
                    candidate.raw,
                    numeric_values[key],
                    candidate.method,
                    candidate.ratio,
                )

        update_start = time.perf_counter()
        audit_record = build_audit_record(page_id, title, best, numeric_values, notes)

        updates_internal: Dict[str, Dict] = {}

        for key, cfg in CATEGORY_CONFIG.items():
            property_name = cfg["property"]
            numeric_value = numeric_values.get(key)
            prop = properties.get(property_name)

            if numeric_value is None:
                continue

            if not prop:
                logger.debug("Property %s missing on page %s", property_name, title)
                audit_record.notes.append(f"missing_property:{property_name}")
                continue

            if prop.get("type") != "number":
                logger.debug("Property %s is not number on page %s", property_name, title)
                audit_record.notes.append(f"non_number_property:{property_name}")
                continue

            current_value = prop.get("number")
            if current_value == numeric_value:
                logger.debug("Property %s already set to %s", property_name, numeric_value)
                continue

            raw_display = best.get(key).raw if best.get(key) else str(numeric_value)
            logger.info("Setting %s to %s (raw '%s')", property_name, numeric_value, raw_display)
            updates_internal[property_name] = {"number": numeric_value}

        if updates_internal:
            logger.info("Prepared updates for %s: %s", title, list(updates_internal.keys()))
        else:
            logger.info("No updates required for %s", title)

        if args.dry_run and updates_internal:
            logger.info("Dry run enabled; not writing updates for %s", title)
        elif updates_internal:
            update_page_properties(client, page_id, updates_internal)

            if config.external_database_id:
                external_page_id = find_external_page_id(client, config.external_database_id, title)
                if external_page_id:
                    try:
                        update_page_properties(client, external_page_id, updates_internal)
                    except Exception as exc:  # pragma: no cover - Notion failure
                        logger.warning(
                            "Failed to update external page %s for %s: %s",
                            external_page_id,
                            title,
                            exc,
                        )
                else:
                    audit_record.notes.append("no_external_match")

        update_done = time.perf_counter()
        logger.info(
            "Timing %s - fetch %.2fs, parse %.2fs, update %.2fs",
            title,
            fetch_done - start_time,
            extract_done - fetch_done,
            update_done - update_start,
        )

        return audit_record, True

    target_count = args.max_items if args.max_items else float("inf")
    processed_count = 0
    pending_pages: List[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        page_iterator = iter(pages_iter)
        exhausted = False

        while processed_count < target_count:
            while len(pending_pages) < args.page_size and processed_count < target_count:
                if exhausted:
                    break
                try:
                    pending_pages.append(next(page_iterator))
                except StopIteration:
                    exhausted = True
                    break

            if not pending_pages:
                break

            futures = [executor.submit(process_page, page) for page in pending_pages]
            pending_pages = []

            future_results = []
            for future in futures:
                try:
                    future_results.append(future.result())
                except Exception as exc:  # pragma: no cover - unexpected exception
                    logger.error("Unexpected error during processing: %s", exc)
            for record, counted in future_results:
                audit_records.append(record)
                if counted:
                    processed_count += 1
                if processed_count >= target_count:
                    break

            if exhausted and not pending_pages:
                if processed_count >= target_count:
                    break
                if not futures:
                    break

    write_audit_csv(audit_records, args.csv_path)


if __name__ == "__main__":
    main()
