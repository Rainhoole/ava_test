"""
Notion Updater Module
====================
This module provides functionality to update existing Notion database items
with research results, rather than creating new pages.
"""

import logging
import re
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import pytz
from notion_client import Client
import os
import yaml
import mistune

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

logger = logging.getLogger(__name__)


FRACTION_RE = re.compile(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")

SCORE_CATEGORIES = [
    {
        "key": "founder_pattern",
        "property": "Founder Pattern",
        "synonyms": ["Founder Pattern"],
        "allow_small_denominator": False,
    },
    {
        "key": "idea_pattern",
        "property": "Idea Pattern",
        "synonyms": ["Idea Pattern"],
        "allow_small_denominator": False,
    },
    {
        "key": "structural_advantage",
        "property": "Structural Advantage",
        "synonyms": ["Structural Advantage"],
        "allow_small_denominator": False,
    },
    {
        "key": "asymmetric_signal",
        "property": "Asymmetric Signal",
        "synonyms": ["Asymmetric Signal", "Asymmetric Signals"],
        "allow_small_denominator": True,
    },
]


class NotionUpdater:
    """Handle updates to existing Notion database items"""
    
    def __init__(self, notion_client: Client, database_id: str):
        self.notion = notion_client
        self.database_id = database_id
        self.eastern = pytz.timezone('America/New_York')
        self.config = self._load_config()
        self.markdown_parser = mistune.create_markdown(renderer='ast')
        self._llm_client = None
    
    def _load_config(self) -> Dict:
        """Load the notion format configuration"""
        config_path = os.path.join(os.path.dirname(__file__), 'notion_format_config.yaml')
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config file: {e}. Using defaults.")
            return {
                'metadata': [],
                'sections': [],
                'inline_formatting': {},
                'paragraphs': {'min_words': 3, 'join_consecutive': True}
            }
    
    def _get_eastern_time(self) -> str:
        """Get current time in Eastern Time (New York)"""
        utc_now = datetime.now(pytz.UTC)
        eastern_now = utc_now.astimezone(self.eastern)
        return eastern_now.strftime('%Y-%m-%d %I:%M:%S %p ET')
    
    def update_item_with_research(
        self,
        page_id: str,
        project_name: str,
        research_content: str,
        project_dir: str = None,
    ) -> str:
        """
        Update an existing database item with research results.
        
        Args:
            page_id: The ID of the Notion page to update
            project_name: Name of the project (for logging)
            research_content: The full research report in markdown format
            project_dir: Path to the project directory containing reasoning file (optional)
            
        Returns:
            The URL of the updated page
        """
        try:
            # Step 1: Extract priority and stage once for both updates
            priority = self._extract_priority(research_content)
            stage = self._extract_stage(research_content)
            categories = self._extract_categories(research_content)
            monitor_flag = self._extract_monitor_flag(research_content)

            # Step 2: Update page properties
            self._update_page_properties(page_id, priority, stage, categories)

            # Step 2a: Update score properties
            score_updates = self._build_score_updates(research_content)
            if score_updates:
                self._apply_score_updates(page_id, score_updates)
            else:
                score_updates = {}

            # Step 3: Append research content to the page
            self._append_research_content_to_page(page_id, research_content)
            
            # Step 5: Try to create reasoning child page if project_dir provided
            reasoning_page_url = None
            if project_dir:
                logger.info(f"Project directory provided for {project_name}: {project_dir}")
                # Check if the reasoning file exists in this directory
                reasoning_path = os.path.join(project_dir, '02_reasoning.md')
                if os.path.exists(reasoning_path):
                    logger.info(f"Found reasoning file at: {reasoning_path}")
                    reasoning_page_url = self._create_reasoning_child_page(page_id, project_name, project_dir)
                    if reasoning_page_url:
                        logger.info(f"Successfully created reasoning child page (will appear automatically in Notion)")
                else:
                    logger.warning(f"No reasoning file found at: {reasoning_path}")
            else:
                logger.info(f"No project directory provided for {project_name}, skipping reasoning page creation")
            
            # Step 6: Get and return the page URL
            page = self.notion.pages.retrieve(page_id=page_id)
            url = page.get('url', '')
            
            logger.info(f"Successfully updated {project_name} (ID: {page_id})")

            # Step 7: Try to update external database if configured
            self._update_external_database(
                project_name,
                priority,
                stage,
                categories,
                research_content,
                score_updates,
                monitor_flag,
            )

            return url
            
        except Exception as e:
            logger.error(f"Error updating Notion item: {e}")
            # Update status to error
            self.update_status(page_id, "error")
            raise
    
    def update_status(self, page_id: str, status: str):
        """Update only the Research Status of a page"""
        try:
            properties = {
                "Research Status": {
                    "multi_select": [{"name": status}]
                }
            }
            
            # If status is error, also set priority to Error
            if status == "error":
                properties["Ava's Priority"] = {
                    "select": {"name": "Error"}
                }
                logger.info(f"Setting priority to Error for error status")
            
            self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )
            logger.info(f"Updated status of {page_id} to: {status}")
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            raise
    
    def _update_page_properties(
        self,
        page_id: str,
        priority: str,
        stage: Optional[str],
        categories: Optional[List[str]],
    ):
        """Update the database properties with research metadata"""
        properties = {
            "Research Status": {
                "multi_select": [{"name": "completed"}]
            },
            "Research Date": {
                "date": {"start": datetime.now().isoformat()}
            },
            "Ava's Priority": {
                "select": {"name": priority}
            }
        }

        # Add stage if it was successfully extracted
        if stage:
            properties["Stage"] = {
                "select": {"name": stage}
            }
            logger.info(f"Setting Stage property to: {stage}")
        else:
            logger.info("No stage to set - leaving Stage field unchanged")

        category_list = [c for c in (categories or []) if c and str(c).strip()]
        if not category_list:
            category_list = ["Unknown"]
        properties["Category"] = {
            "multi_select": [{"name": str(cat).strip()} for cat in category_list]
        }

        # Update only the properties that exist in the database
        # The research content will be appended as blocks to the page content area
        try:
            self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )
        except Exception as e:
            error_str = str(e)
            retried = False
            if stage and "Stage" in error_str:
                logger.warning(f"Stage field error: {e}. Retrying without stage...")
                properties.pop("Stage", None)
                retried = True
            if "Category" in error_str:
                logger.warning(f"Category field error: {e}. Retrying without Category...")
                properties.pop("Category", None)
                retried = True
            if retried:
                self.notion.pages.update(page_id=page_id, properties=properties)
            else:
                raise

    def _build_score_updates(self, markdown: str) -> Dict[str, Dict]:
        """Extract score values from markdown and build Notion property updates."""
        scores = self._extract_category_scores(markdown)
        updates: Dict[str, Dict] = {}
        for category in SCORE_CATEGORIES:
            property_name = category["property"]
            value = scores.get(property_name)
            if value is None:
                continue
            updates[property_name] = {"number": value}
        return updates

    def _apply_score_updates(self, page_id: str, score_updates: Dict[str, Dict]):
        if not score_updates:
            return
        try:
            self.notion.pages.update(
                page_id=page_id,
                properties=score_updates
            )
            logger.info(
                "Updated score properties: %s",
                ", ".join(f"{name}={value['number']}" for name, value in score_updates.items())
            )
        except Exception as exc:
            logger.warning("Failed to update score properties for %s: %s", page_id, exc)

    def _extract_category_scores(self, markdown: str) -> Dict[str, Optional[float]]:
        candidates: Dict[str, Dict] = {}
        lines = markdown.splitlines()

        for category in SCORE_CATEGORIES:
            result = self._extract_with_regex(lines, category)
            if result:
                candidates[category["key"]] = result

        if len(candidates) < 3:
            llm_matches = self._call_llm_fallback(markdown)
            for key, match in llm_matches.items():
                if key not in candidates and match:
                    candidates[key] = match

        scores: Dict[str, Optional[float]] = {}
        for category in SCORE_CATEGORIES:
            key = category["key"]
            property_name = category["property"]
            candidate = candidates.get(key)
            if candidate and candidate.get("numeric") is not None:
                scores[property_name] = candidate["numeric"]
                logger.debug(
                    "Extracted %s score: raw='%s' numeric=%s method=%s",
                    property_name,
                    candidate.get("raw"),
                    candidate.get("numeric"),
                    candidate.get("method"),
                )
            else:
                scores[property_name] = -1.0
                logger.debug("Defaulting %s score to -1", property_name)
        return scores

    def _extract_with_regex(self, lines: List[str], category: Dict) -> Optional[Dict]:
        best_candidate = None
        synonyms = [syn.lower() for syn in category["synonyms"]]

        for idx, line in enumerate(lines):
            lowered = line.lower()
            if not any(syn in lowered for syn in synonyms):
                continue

            raw = self._find_score_in_line(line, category["allow_small_denominator"])
            if not raw and idx + 1 < len(lines):
                raw = self._find_score_in_line(lines[idx + 1], category["allow_small_denominator"])
            if not raw:
                continue

            numeric = self._convert_raw_to_number(raw, category["allow_small_denominator"])
            ratio = self._compute_ratio(raw, category["allow_small_denominator"])
            candidate = {
                "raw": raw.strip(),
                "numeric": numeric,
                "ratio": ratio,
                "method": "regex_structured",
            }

            if best_candidate is None:
                best_candidate = candidate
                continue

            if (candidate["ratio"] or -1) > (best_candidate["ratio"] or -1):
                best_candidate = candidate

        return best_candidate

    def _find_score_in_line(self, line: str, allow_small_denominator: bool) -> Optional[str]:
        for match in FRACTION_RE.finditer(line):
            numerator, denominator = self._clean_fraction(match.group(0))
            if numerator is None or denominator is None:
                continue
            if not allow_small_denominator and denominator <= 4:
                continue
            return match.group(0)

        for match in PERCENT_RE.finditer(line):
            return match.group(0)

        return None

    def _convert_raw_to_number(self, raw: str, allow_small_denominator: bool) -> Optional[float]:
        stripped = raw.strip()
        if "/" in stripped:
            numerator, denominator = self._clean_fraction(stripped)
            if numerator is None or denominator is None:
                return None
            if not allow_small_denominator and denominator <= 4:
                return None
            return numerator
        if stripped.endswith("%"):
            try:
                return float(stripped.rstrip("% "))
            except ValueError:
                return None
        return None

    def _clean_fraction(self, raw: str) -> Tuple[Optional[float], Optional[float]]:
        numbers = re.findall(r"\d+(?:\.\d+)?", raw)
        if len(numbers) != 2:
            return None, None
        numerator = float(numbers[0])
        denominator = float(numbers[1])
        if denominator <= 0:
            return None, None
        return numerator, denominator

    def _compute_ratio(self, raw: str, allow_small_denominator: bool) -> Optional[float]:
        stripped = raw.strip()
        if "/" in stripped:
            numerator, denominator = self._clean_fraction(stripped)
            if numerator is None or denominator is None:
                return None
            if not allow_small_denominator and denominator <= 4:
                return None
            return max(0.0, min(1.0, numerator / denominator))
        if stripped.endswith("%"):
            try:
                value = float(stripped.rstrip("% "))
            except ValueError:
                return None
            return max(0.0, min(1.0, value / 100))
        return None

    def _call_llm_fallback(self, markdown: str) -> Dict[str, Dict]:
        client = self._get_llm_client()
        if not client:
            return {}

        system_prompt = (
            "Extract the explicit numeric scores for these categories: Founder Pattern, Idea Pattern, "
            "Structural Advantage, Asymmetric Signal. Return JSON with keys founder_pattern, "
            "idea_pattern, structural_advantage, asymmetric_signal. Each value must be an object with "
            "fields raw (string or null) and matched (string or null). Only copy numbers that appear in "
            "the text verbatim. If a category has no explicit number, set both fields to null."
        )
        user_prompt = f"Report text:\n{markdown}\n\nRemember: only extract numbers exactly present in the text."

        try:
            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("LLM fallback failed: %s", exc)
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
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("LLM fallback produced invalid JSON; ignoring")
            return {}

        matches: Dict[str, Dict] = {}
        for category in SCORE_CATEGORIES:
            key = category["key"]
            entry = data.get(key)
            if not isinstance(entry, dict):
                continue
            raw = entry.get("raw")
            matched = entry.get("matched")
            if not raw or not matched:
                continue
            if raw not in markdown and matched not in markdown:
                continue
            numeric = self._convert_raw_to_number(raw, category["allow_small_denominator"])
            ratio = self._compute_ratio(raw, category["allow_small_denominator"])
            matches[key] = {
                "raw": raw,
                "numeric": numeric,
                "ratio": ratio,
                "method": "llm_fallback",
            }
        return matches

    def _get_llm_client(self):
        if OpenAI is None:
            return None
        if self._llm_client is not None:
            return self._llm_client
        try:
            self._llm_client = OpenAI()
        except Exception as exc:
            logger.warning("Unable to initialize OpenAI client: %s", exc)
            self._llm_client = None
        return self._llm_client
    
    def _prepare_research_blocks(self, research_content: str) -> List[Dict]:
        """Prepare all blocks for the research content including header"""
        blocks = []
        
        # Add header blocks
        blocks.extend([
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "🤖 Ava's Report"}
                    }]
                }
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": f"Generated by Ava's Research Agent Alice - {self._get_eastern_time()}"
                        }
                    }],
                    "icon": {"emoji": "📊"},
                    "color": "blue_background"
                }
            }
        ])
        
        # Convert markdown to Notion blocks and add to the list
        content_blocks = self._markdown_to_notion_blocks(research_content)
        blocks.extend(content_blocks)
        
        logger.info(f"Prepared {len(blocks)} total blocks for Notion upload")
        logger.debug(f"Block types: {[b.get('type') for b in blocks[:10]]}")  # First 10 block types
        
        return blocks

    def _build_report_header_blocks(self) -> List[Dict]:
        """Build the standard header blocks shown before the report content."""
        return [
            {
                "object": "block",
                "type": "divider",
                "divider": {},
            },
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": "🤖 Ava's Report"}}]
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": f"Generated by Ava's Research Agent Alice - {self._get_eastern_time()}"
                            },
                        }
                    ],
                    "icon": {"emoji": "📊"},
                    "color": "blue_background",
                },
            },
        ]

    def _append_children_with_retry(self, parent_block_id: str, children: List[Dict]) -> List[Dict]:
        """Append a single batch of children blocks and return created blocks."""
        for attempt in range(2):  # initial + 1 retry for transient errors
            try:
                response = self.notion.blocks.children.append(
                    block_id=parent_block_id,
                    children=children,
                )
                return response.get("results", [])
            except Exception as exc:
                error_str = str(exc)
                if attempt == 0 and any(code in error_str for code in ("500", "502", "503")):
                    logger.warning(
                        "Append failed with %s, retrying once...", exc.__class__.__name__
                    )
                    import time

                    time.sleep(1)
                    continue
                raise
        return []

    def _strip_redundant_section_heading(self, section_name: str, content: str) -> str:
        """Remove the leading markdown heading that duplicates the section marker title."""
        if not content:
            return ""

        lines = content.splitlines()
        idx = 0
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return ""

        heading_match = re.match(r"^\s*#{1,6}\s*(.+?)\s*$", lines[idx])
        if not heading_match:
            return content.strip()

        heading_text = heading_match.group(1).strip()
        if heading_text.lower() != section_name.strip().lower():
            return content.strip()

        idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        return "\n".join(lines[idx:]).strip()

    def _extract_confidence_check(self, content: str) -> Tuple[str, Optional[str]]:
        """Extract a trailing **Confidence Check:** paragraph, if present."""
        if not content:
            return "", None

        matches = list(re.finditer(r"\*\*Confidence Check:\*\*", content, flags=re.IGNORECASE))
        if not matches:
            return content.strip(), None

        last = matches[-1]
        confidence_md = content[last.start() :].strip()
        main_md = content[: last.start()].rstrip()
        return main_md.strip(), confidence_md

    def _split_paragraphs(self, markdown: str) -> List[str]:
        """Split markdown into rough paragraphs (blank-line delimited)."""
        if not markdown or not markdown.strip():
            return []
        parts = re.split(r"\n\s*\n", markdown.strip())
        return [p.strip() for p in parts if p.strip()]

    def _strip_summary_label(self, paragraph_md: str) -> str:
        """Remove leading TL;DR or Summary label for display."""
        if not paragraph_md:
            return ""
        return re.sub(
            r"^\s*(TL;?DR|TLDR|Summary)\s*:\s*",
            "",
            paragraph_md.strip(),
            flags=re.IGNORECASE,
        )

    def _split_section_summary_and_details(self, content: str) -> Tuple[str, str]:
        """Split section markdown into a 1-paragraph summary and remaining details."""
        if not content or not content.strip():
            return "", ""

        details_marker = re.search(
            r"^\s*#{2,6}\s*Details\s*$",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        if details_marker:
            prefix = content[: details_marker.start()].strip()
            details = content[details_marker.end() :].strip()

            prefix_paragraphs = self._split_paragraphs(prefix)
            if prefix_paragraphs:
                summary = self._strip_summary_label(prefix_paragraphs[0])
                leftover_prefix = "\n\n".join(prefix_paragraphs[1:]).strip()
                if leftover_prefix:
                    details = f"{leftover_prefix}\n\n{details}".strip()
                return summary, details

            details_paragraphs = self._split_paragraphs(details)
            if details_paragraphs:
                summary = self._strip_summary_label(details_paragraphs[0])
                remaining = "\n\n".join(details_paragraphs[1:]).strip()
                return summary, remaining

            return "", ""

        paragraphs = self._split_paragraphs(content)
        if not paragraphs:
            return "", ""

        summary_idx = None
        for idx, paragraph in enumerate(paragraphs):
            if re.match(r"^\s*(TL;?DR|TLDR|Summary)\s*:\s*", paragraph, flags=re.IGNORECASE):
                summary_idx = idx
                break

        if summary_idx is None:
            for idx, paragraph in enumerate(paragraphs):
                if paragraph.lstrip().startswith("#"):
                    continue
                if len(paragraph.split()) < 8:
                    continue
                summary_idx = idx
                break

        if summary_idx is None:
            summary_idx = 0

        summary = self._strip_summary_label(paragraphs[summary_idx])
        details_parts = paragraphs[:summary_idx] + paragraphs[summary_idx + 1 :]
        details = "\n\n".join(details_parts).strip()
        return summary, details

    def _build_details_toggle_block(self) -> Dict:
        """Create an empty toggle block; children are appended separately."""
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "Details"}}],
            },
        }

    def _append_section_summary_and_toggle(
        self, page_id: str, section_name: str, section_content: str
    ) -> None:
        """Append section header + summary + confidence + details toggle (details as toggle children)."""
        cleaned = self._strip_redundant_section_heading(section_name, section_content or "")
        cleaned, confidence_md = self._extract_confidence_check(cleaned)
        summary_md, details_md = self._split_section_summary_and_details(cleaned)

        if not summary_md and details_md:
            details_paragraphs = self._split_paragraphs(details_md)
            if details_paragraphs:
                summary_md = self._strip_summary_label(details_paragraphs[0])
                details_md = "\n\n".join(details_paragraphs[1:]).strip()

        top_level_blocks: List[Dict] = [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": section_name}}]
                },
            }
        ]

        if summary_md:
            top_level_blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": self._parse_inline_formatting(summary_md)},
                }
            )

        toggle_block = self._build_details_toggle_block()
        top_level_blocks.append(toggle_block)

        created = self._append_children_with_retry(page_id, top_level_blocks)
        toggle_id = None
        for created_block in created:
            if created_block.get("type") == "toggle":
                toggle_id = created_block.get("id")
                break

        if not toggle_id:
            logger.warning("Unable to locate created toggle block id for section '%s'", section_name)
            fallback_blocks: List[Dict] = []
            if details_md.strip():
                fallback_blocks.extend(self._process_section_content(details_md))
            if confidence_md:
                fallback_blocks.append(
                    {
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": self._parse_inline_formatting(confidence_md),
                            "icon": {"emoji": "🔎"},
                            "color": "gray_background",
                        },
                    }
                )
            if fallback_blocks:
                self._append_blocks_to_page(page_id, fallback_blocks)
            return

        toggle_children: List[Dict] = []
        if details_md.strip():
            toggle_children.extend(self._process_section_content(details_md))
        if confidence_md:
            toggle_children.append(
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": self._parse_inline_formatting(confidence_md),
                        "icon": {"emoji": "🔎"},
                        "color": "gray_background",
                    },
                }
            )
        if toggle_children:
            self._append_blocks_to_page(toggle_id, toggle_children)

    def _append_research_content_to_page(self, page_id: str, research_content: str) -> None:
        """Append report header + content, formatting each section as Summary + Details toggle."""
        header_blocks = self._build_report_header_blocks()
        self._append_blocks_to_page(page_id, header_blocks)

        # Structured format detection (REPORT START/END)
        report_start_pattern = r"===\s*REPORT\s+START\s*==="
        report_end_pattern = r"===\s*REPORT\s+END\s*==="

        if not re.search(report_start_pattern, research_content or ""):
            logger.warning("No structured format detected, using legacy parser")
            legacy_blocks = self._markdown_to_notion_blocks_legacy(research_content or "")
            self._append_blocks_to_page(page_id, legacy_blocks)
            return

        start_match = re.search(report_start_pattern, research_content)
        end_match = re.search(report_end_pattern, research_content)
        structured_md = research_content
        if start_match and end_match:
            structured_md = research_content[start_match.start() : end_match.end()]

        metadata = self._extract_metadata(structured_md)
        meta_configs = {cfg.get("name"): cfg for cfg in self.config.get("metadata", [])}

        meta_blocks: List[Dict] = []
        for name, value in metadata.items():
            if name in meta_configs:
                meta_config = meta_configs[name]
                icon = meta_config.get("icon", "📌")
                color = meta_config.get("color", "gray_background")
                display_name = name.upper()
            else:
                icon = "📌"
                color = "gray_background"
                if name.startswith("meta_"):
                    display_name = name[5:].upper().replace("_", " ")
                else:
                    display_name = name.upper().replace("_", " ")

            display_value = value
            if name in ("categories", "meta_categories") and value:
                parsed = self._parse_categories_value(str(value))
                if parsed:
                    display_value = ", ".join(parsed)

            meta_blocks.append(
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"{display_name}: {display_value}"},
                            }
                        ],
                        "icon": {"emoji": icon},
                        "color": color,
                    },
                }
            )

        if meta_blocks:
            self._append_blocks_to_page(page_id, meta_blocks)

        sections = self._extract_sections(structured_md)
        if not sections:
            logger.error("No sections found in structured format; falling back to legacy parser")
            legacy_blocks = self._markdown_to_notion_blocks_legacy(structured_md)
            self._append_blocks_to_page(page_id, legacy_blocks)
            return

        for section_name, section_content in sections:
            self._append_section_summary_and_toggle(page_id, section_name, section_content)
    
    def _append_blocks_to_page(self, page_id: str, blocks: List[Dict]):
        """Append blocks to a page in batches with retry logic"""
        # Append blocks in batches (Notion limit is 100 blocks per request)
        batch_size = 50
        logger.info(f"Appending {len(blocks)} blocks to page {page_id} in batches of {batch_size}")
        
        successful_batches = 0
        failed_batches = []
        
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i:i + batch_size]
            batch_num = i//batch_size + 1
            logger.debug(f"Appending batch {batch_num}: {len(batch)} blocks")
            
            # Try to upload batch with one retry
            success = False
            for attempt in range(2):  # Try twice (initial + 1 retry)
                try:
                    self.notion.blocks.children.append(block_id=page_id, children=batch)
                    logger.debug(f"Successfully appended batch {batch_num}")
                    successful_batches += 1
                    success = True
                    break
                except Exception as e:
                    error_str = str(e)
                    if attempt == 0 and ("500" in error_str or "502" in error_str or "503" in error_str):
                        logger.warning(f"Batch {batch_num} failed with {e.__class__.__name__}, retrying...")
                        import time
                        time.sleep(1)  # Wait 1 second before retry
                    else:
                        logger.error(f"Batch {batch_num} failed after {attempt + 1} attempt(s): {e}")
                        # Log the first few blocks of the failed batch for debugging
                        if len(batch) > 0:
                            logger.debug(f"Failed batch preview (first block type): {batch[0].get('type', 'unknown')}")
                        break
            
            if not success:
                failed_batches.append(batch_num)
                # Continue with next batch instead of raising
                logger.warning(f"Continuing despite batch {batch_num} failure...")
        
        # Report results
        total_batches = (len(blocks) + batch_size - 1) // batch_size
        logger.info(f"Upload complete: {successful_batches}/{total_batches} batches successful")
        
        if failed_batches:
            logger.error(f"Failed batches: {failed_batches}")
            # Only raise if ALL batches failed
            if successful_batches == 0:
                raise Exception(f"Failed to upload any blocks to Notion. All {len(failed_batches)} batches failed.")
            else:
                logger.warning(f"Partial upload: {successful_batches} batches succeeded, {len(failed_batches)} failed")
    
    def _extract_sections(self, markdown: str) -> List[Tuple[str, str]]:
        """Extract sections from structured markdown, maintaining order"""
        sections = []
        current_section = None
        current_content = []
        
        # Look for section markers - ultra flexible to handle any spacing
        lines = markdown.split('\n')
        for line in lines:
            # Check for section start - handle any spacing combination
            # Matches: ===SECTION:Name===, === SECTION: Name ===, etc.
            section_match = re.match(r'^===\s*SECTION\s*:\s*(.+?)\s*===\s*$', line)
            if section_match:
                # Save previous section if exists
                if current_section:
                    sections.append((current_section, '\n'.join(current_content).strip()))
                current_section = section_match.group(1).strip()
                current_content = []
                logger.debug(f"Found section start: '{current_section}'")
            # Check for section end - handle any spacing
            elif re.match(r'^===\s*END\s+SECTION\s*===\s*$', line.strip()) and current_section:
                # End of section
                sections.append((current_section, '\n'.join(current_content).strip()))
                logger.debug(f"Found section end for: '{current_section}'")
                current_section = None
                current_content = []
            elif current_section:
                # Add to current section
                current_content.append(line)
        
        # Handle any remaining content
        if current_section and current_content:
            sections.append((current_section, '\n'.join(current_content).strip()))
            logger.debug(f"Added remaining content for section: '{current_section}'")
            
        logger.info(f"Extracted {len(sections)} sections: {[s[0] for s in sections[:5]]}")  # Log first 5 section names
        return sections
    
    def _extract_metadata(self, markdown: str) -> Dict[str, str]:
        """Extract metadata from structured markdown - handles multiple styles"""
        metadata = {}
        
        # Look for configured patterns first (highest priority)
        for pattern_config in self.config.get('metadata', []):
            pattern = pattern_config['pattern']
            name = pattern_config.get('name', 'unknown')
            match = re.search(pattern, markdown, re.MULTILINE)
            if match:
                metadata[name] = match.group(1)
        
        # Pattern 1: META_ prefix style (e.g., META_PRIORITY: High)
        generic_meta_pattern = r'^META_([A-Z_]+):\s*(.+)$'
        for match in re.finditer(generic_meta_pattern, markdown, re.MULTILINE):
            field_name = match.group(1).lower()
            field_value = match.group(2).strip()
            # Only add if not already captured by specific patterns
            if field_name not in metadata:
                metadata[f'meta_{field_name}'] = field_value
                logger.info(f"Found META_ field: META_{match.group(1)} = '{field_value}'")
        
        # Pattern 2: Simple key-value at start (e.g., "Priority: High" right after REPORT START)
        # Look for lines between REPORT START and first SECTION marker
        report_start = markdown.find('=== REPORT START ===')
        first_section = markdown.find('=== SECTION:')
        
        if report_start != -1 and first_section != -1:
            header_area = markdown[report_start:first_section]
            # Match "Key: Value" patterns (capitalized keys)
            simple_kv_pattern = r'^([A-Z][A-Za-z\s]+):\s*(.+)$'
            for match in re.finditer(simple_kv_pattern, header_area, re.MULTILINE):
                key = match.group(1).strip()
                value = match.group(2).strip()
                # Skip the REPORT START line itself and section markers
                if key not in ['REPORT START', 'SECTION', 'END SECTION', 'REPORT END']:
                    normalized_key = key.lower().replace(' ', '_')
                    # Only add if not already captured
                    if normalized_key not in metadata and f'meta_{normalized_key}' not in metadata:
                        metadata[normalized_key] = value
                        logger.info(f"Found simple metadata: {key} = '{value}'")
        
        # Pattern 3: Markdown front matter style (YAML between --- markers)
        yaml_pattern = r'^---\s*\n(.*?)\n---\s*$'
        yaml_match = re.search(yaml_pattern, markdown, re.MULTILINE | re.DOTALL)
        if yaml_match:
            try:
                import yaml
                front_matter = yaml.safe_load(yaml_match.group(1))
                if isinstance(front_matter, dict):
                    for key, value in front_matter.items():
                        normalized_key = str(key).lower().replace(' ', '_').replace('-', '_')
                        if normalized_key not in metadata:
                            metadata[normalized_key] = str(value)
                            logger.info(f"Found YAML metadata: {key} = '{value}'")
            except:
                pass  # Ignore YAML parsing errors
                
        return metadata
    
    def _markdown_to_notion_blocks(self, markdown: str) -> List[Dict]:
        """Convert markdown content to Notion block format with improved structured parsing"""
        blocks = []
        
        logger.info(f"Converting markdown to Notion blocks. Content length: {len(markdown)} chars")
        logger.debug(f"First 200 chars: {markdown[:200]}")
        
        # First check if we have structured format - flexible regex
        # Match variations like ===REPORT START===, === REPORT START ===, etc.
        report_start_pattern = r'===\s*REPORT\s+START\s*==='
        report_end_pattern = r'===\s*REPORT\s+END\s*==='
        
        if re.search(report_start_pattern, markdown):
            logger.info("Detected structured format with REPORT START marker")
            
            # Extract only the content between REPORT START and REPORT END
            start_match = re.search(report_start_pattern, markdown)
            end_match = re.search(report_end_pattern, markdown)
            
            start_idx = start_match.start() if start_match else -1
            end_idx = end_match.end() if end_match else -1
            
            if start_idx != -1 and end_idx != -1:
                # Use only the structured content, ignoring anything before/after
                markdown = markdown[start_idx:end_idx]
                logger.info(f"Extracted structured content: {len(markdown)} chars")
            else:
                logger.warning("Found REPORT START but missing REPORT END marker")
            # Extract metadata
            metadata = self._extract_metadata(markdown)
            
            # Create a mapping of metadata names to their configs
            meta_configs = {cfg.get('name'): cfg for cfg in self.config.get('metadata', [])}
            
            # Add all metadata as callout blocks
            for name, value in metadata.items():
                # Check if this metadata field has a specific configuration
                if name in meta_configs:
                    # Use configured settings
                    meta_config = meta_configs[name]
                    icon = meta_config.get('icon', '📌')
                    color = meta_config.get('color', 'gray_background')
                    display_name = name.upper()
                else:
                    # Use defaults for unconfigured fields
                    icon = '📌'
                    color = 'gray_background'
                    # Format display name from meta_field_name to FIELD NAME
                    if name.startswith('meta_'):
                        display_name = name[5:].upper().replace('_', ' ')
                    else:
                        display_name = name.upper().replace('_', ' ')
                
                callout_block = {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": f"{display_name}: {value}"}
                        }],
                        "icon": {"emoji": icon},
                        "color": color
                    }
                }
                blocks.append(callout_block)
                logger.debug(f"Added callout for metadata: {display_name} = {value}")
            
            # Extract and process sections
            sections = self._extract_sections(markdown)
            logger.info(f"Extracted {len(sections)} sections from structured format")
            
            if not sections:
                logger.error("No sections found in structured format! Check section markers.")
                # Fallback to legacy parser
                logger.warning("Falling back to legacy parser due to missing sections")
                return self._markdown_to_notion_blocks_legacy(markdown)
            
            for section_name, section_content in sections:
                logger.debug(f"Processing section: {section_name} ({len(section_content)} chars)")
                # Add section header
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": section_name}
                        }]
                    }
                })
                
                # Process section content
                if section_content:
                    section_blocks = self._process_section_content(section_content)
                    blocks.extend(section_blocks)
                else:
                    logger.warning(f"Section '{section_name}' has no content")
                    
        else:
            # Fallback to old parsing method for backward compatibility
            logger.warning("No structured format detected, using legacy parser")
            blocks = self._markdown_to_notion_blocks_legacy(markdown)
            
        return blocks
    
    def _process_section_content(self, content: str) -> List[Dict]:
        """Process content within a section using mistune AST"""
        blocks = []
        
        # Parse with mistune to get AST
        ast = self.markdown_parser(content)
        
        # Log AST structure for debugging lists
        for i, node in enumerate(ast):  # Log all nodes for debugging
            node_type = node.get('type')
            if node_type in ['list', 'paragraph']:
                if node_type == 'list':
                    logger.debug(f"AST node {i}: LIST (ordered={node.get('attrs', {}).get('ordered')})")
                    # Log list children
                    for j, child in enumerate(node.get('children', [])):
                        if child.get('type') == 'list_item':
                            item_text = self._extract_text_from_children(child.get('children', []))
                            logger.debug(f"  List item {j}: '{item_text[:100]}'")
                else:
                    text = self._extract_text_from_children(node.get('children', []))
                    logger.debug(f"AST node {i}: paragraph - '{text[:100]}'")
        
        # Convert AST to Notion blocks
        for node in ast:
            notion_blocks = self._ast_node_to_notion_blocks(node)
            if notion_blocks:
                blocks.extend(notion_blocks)
                
        return blocks
    
    def _ast_node_to_notion_blocks(self, node: Dict) -> List[Dict]:
        """Convert a mistune AST node to Notion blocks"""
        blocks = []
        node_type = node.get('type')
        
        if node_type == 'heading':
            level = node.get('attrs', {}).get('level', 2)
            heading_type = f'heading_{min(level, 3)}'  # Notion only supports 1-3
            text = self._extract_text_from_children(node.get('children', []))
            
            blocks.append({
                "object": "block",
                "type": heading_type,
                heading_type: {
                    "rich_text": self._parse_inline_formatting(text)
                }
            })
            
        elif node_type == 'paragraph':
            text = self._extract_text_from_children(node.get('children', []))
            if text.strip():
                # Debug logging for list detection
                if re.match(r'^\d+\.', text.strip()):
                    logger.debug(f"Potential numbered list detected: {text.strip()[:100]}")
                
                # Check if this paragraph is actually a numbered list item
                numbered_match = re.match(r'^(\d+)\.\s*(.*)$', text.strip())
                bullet_match = re.match(r'^[•·]\s*(.*)$', text.strip())
                
                if numbered_match:
                    # Convert to numbered list item
                    list_text = numbered_match.group(2).strip()
                    logger.debug(f"Numbered list regex matched: num='{numbered_match.group(1)}', text='{list_text[:100]}'")
                    # If list text is empty, skip creating the list item
                    if not list_text:
                        logger.warning(f"Skipping empty numbered list item: {text.strip()}")
                    else:
                        blocks.append({
                            "object": "block",
                            "type": "numbered_list_item",
                            "numbered_list_item": {
                                "rich_text": self._parse_inline_formatting(list_text)
                            }
                        })
                elif bullet_match:
                    # Convert to bullet list item
                    list_text = bullet_match.group(1).strip()
                    # If list text is empty, skip creating the list item
                    if not list_text:
                        logger.warning(f"Skipping empty bullet list item: {text.strip()}")
                    else:
                        blocks.append({
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": self._parse_inline_formatting(list_text)
                            }
                        })
                else:
                    # Regular paragraph
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": self._parse_inline_formatting(text)
                        }
                    })
                
        elif node_type == 'list':
            list_type = 'numbered' if node.get('attrs', {}).get('ordered') else 'bulleted'
            logger.debug(f"Processing {list_type} list with {len(node.get('children', []))} items")
            for idx, item in enumerate(node.get('children', [])):
                if item.get('type') == 'list_item':
                    item_text = self._extract_text_from_children(item.get('children', []))
                    logger.debug(f"List item {idx}: '{item_text[:100]}'")
                    if item_text.strip():
                        blocks.append({
                            "object": "block",
                            "type": f"{list_type}_list_item",
                            f"{list_type}_list_item": {
                                "rich_text": self._parse_inline_formatting(item_text)
                            }
                        })
                    else:
                        logger.warning(f"Skipping empty {list_type} list item at index {idx}")
                    
        elif node_type == 'block_code':
            code_text = node.get('raw', '')
            # Split long code blocks if needed
            if len(code_text) > 1900:
                for i in range(0, len(code_text), 1900):
                    chunk = code_text[i:i + 1900]
                    blocks.append({
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": chunk}
                            }],
                            "language": "plain text"
                        }
                    })
            else:
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": code_text}
                        }],
                        "language": "plain text"
                    }
                })
                
        elif node_type == 'thematic_break':
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
        elif node_type == 'block_quote':
            quote_text = self._extract_text_from_children(node.get('children', []))
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": self._parse_inline_formatting(quote_text)
                }
            })
            
        return blocks
    
    def _extract_text_from_children(self, children: List[Dict]) -> str:
        """Extract text from AST children nodes"""
        text_parts = []
        
        for child in children:
            if child.get('type') == 'text':
                text_parts.append(child.get('raw', ''))
            elif child.get('type') == 'strong':
                inner_text = self._extract_text_from_children(child.get('children', []))
                text_parts.append(f'**{inner_text}**')
            elif child.get('type') == 'emphasis':
                inner_text = self._extract_text_from_children(child.get('children', []))
                text_parts.append(f'*{inner_text}*')
            elif child.get('type') == 'code':
                text_parts.append(f'`{child.get("raw", "")}`')
            elif child.get('type') == 'link':
                inner_text = self._extract_text_from_children(child.get('children', []))
                url = child.get('attrs', {}).get('url', '')
                text_parts.append(f'[{inner_text}]({url})')
            elif child.get('type') == 'paragraph':
                # Handle nested paragraphs
                inner_text = self._extract_text_from_children(child.get('children', []))
                text_parts.append(inner_text)
            elif child.get('type') == 'block_text':
                # Handle block_text (used in list items)
                inner_text = self._extract_text_from_children(child.get('children', []))
                text_parts.append(inner_text)
            elif child.get('type') == 'softbreak':
                text_parts.append(' ')
            elif child.get('type') == 'linebreak':
                text_parts.append('\n')
                
        return ''.join(text_parts)
    
    def _markdown_to_notion_blocks_legacy(self, markdown: str) -> List[Dict]:
        """Legacy markdown parsing method for backward compatibility"""
        blocks = []
        lines = markdown.split('\n')
        
        # This is the original line-by-line parsing logic
        in_code_block = False
        code_content = []
        in_table = False
        table_rows = []
        paragraph_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Handle code blocks
            if line.strip().startswith('```'):
                # First, flush any pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                if in_code_block:
                    # End of code block
                    code_text = '\n'.join(code_content)
                    # Split long code blocks if needed
                    if len(code_text) > 1900:
                        # For code blocks that are too long, split into multiple blocks
                        for j in range(0, len(code_text), 1900):
                            chunk = code_text[j:j + 1900]
                            blocks.append({
                                "object": "block",
                                "type": "code",
                                "code": {
                                    "rich_text": [{
                                        "type": "text",
                                        "text": {"content": chunk}
                                    }],
                                    "language": "plain text"
                                }
                            })
                    else:
                        blocks.append({
                            "object": "block",
                            "type": "code",
                            "code": {
                                "rich_text": [{
                                    "type": "text",
                                    "text": {"content": code_text}
                                }],
                                "language": "plain text"
                            }
                        })
                    code_content = []
                    in_code_block = False
                else:
                    # Start of code block
                    in_code_block = True
                i += 1
                continue
            
            if in_code_block:
                code_content.append(line)
                i += 1
                continue
            
            # Handle tables
            if self._is_table_row(line):
                # First, flush any pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                if not in_table:
                    in_table = True
                    table_rows = []
                table_rows.append(line)
                i += 1
                continue
            elif in_table:
                # End of table, process it
                blocks.extend(self._process_table(table_rows))
                in_table = False
                table_rows = []
            
            # Check for headers and special formatting
            if line.startswith('# '):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": line[2:].strip()}
                        }]
                    }
                })
            elif line.startswith('## '):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": line[3:].strip()}
                        }]
                    }
                })
            elif line.startswith('### '):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": line[4:].strip()}
                        }]
                    }
                })
            elif line.strip().startswith('- ') or line.strip().startswith('* ') or line.strip().startswith('• '):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                # Handle bullet points (collect multi-line items)
                content_lines = [re.sub(r'^[\-\*•]\s+', '', line.strip())]
                
                # Look ahead for continuation lines (indented or not starting with a list marker)
                j = i + 1
                while j < len(lines) and lines[j].strip() and not self._is_list_item(lines[j]) and not lines[j].startswith('#'):
                    if lines[j].strip():
                        content_lines.append(lines[j].strip())
                    j += 1
                
                content = ' '.join(content_lines)
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": self._parse_inline_formatting(content)
                    }
                })
                i = j - 1  # Skip the lines we've already processed
            elif self._is_numbered_risk_item(line):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                # Special handling for risk items like "1. Regulatory Overlap – ..."
                blocks.extend(self._process_numbered_risk_item(line, lines, i))
                # Skip to next non-continuation line
                while i + 1 < len(lines) and not self._starts_new_item(lines[i + 1]):
                    i += 1
            elif re.match(r'^\d+\.\s+', line.strip()):
                # Flush pending paragraph
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
                
                # Handle numbered items (collect multi-line items)
                content = re.sub(r'^\d+\.\s+', '', line.strip())
                content_lines = [content]
                
                # Look ahead for continuation lines
                j = i + 1
                while j < len(lines) and lines[j].strip() and not self._is_list_item(lines[j]) and not lines[j].startswith('#'):
                    if lines[j].strip():
                        content_lines.append(lines[j].strip())
                    j += 1
                
                full_content = ' '.join(content_lines)
                
                # Check if it's a section header
                if self._is_section_header(content):
                    blocks.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": line.strip()}
                            }]
                        }
                    })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": self._parse_inline_formatting(full_content)
                        }
                    })
                i = j - 1  # Skip processed lines
            elif line.strip() == '':
                # Empty line - end current paragraph if any
                if paragraph_lines:
                    blocks.append(self._create_paragraph_block(paragraph_lines))
                    paragraph_lines = []
            else:
                # Regular text - accumulate for paragraph
                if line.strip():
                    paragraph_lines.append(line.strip())
            
            i += 1
        
        # Flush any remaining paragraph
        if paragraph_lines:
            blocks.append(self._create_paragraph_block(paragraph_lines))
        
        # Handle any remaining table
        if in_table and table_rows:
            blocks.extend(self._process_table(table_rows))
        
        return blocks
    
    def _create_paragraph_block(self, lines: List[str]) -> Dict:
        """Create a paragraph block from accumulated lines"""
        text = ' '.join(lines)
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": self._parse_inline_formatting(text)
            }
        }
    
    def _is_list_item(self, line: str) -> bool:
        """Check if a line starts a new list item"""
        stripped = line.strip()
        return (stripped.startswith('- ') or 
                stripped.startswith('* ') or 
                stripped.startswith('• ') or
                re.match(r'^\d+\.\s+', stripped) is not None)
    
    def _is_table_row(self, line: str) -> bool:
        """Check if a line is part of a markdown table"""
        return '|' in line and (line.count('|') >= 2)
    
    def _process_table(self, rows: List[str]) -> List[Dict]:
        """Convert markdown table to Notion table blocks"""
        blocks = []
        
        if len(rows) < 2:  # Need at least header and separator
            return blocks
        
        # Parse table
        headers = [cell.strip() for cell in rows[0].split('|')[1:-1]]
        
        # Create table block
        table_block = {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": len(headers),
                "has_column_header": True,
                "has_row_header": False,
                "children": []
            }
        }
        
        # Add header row
        header_row = {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [[{"type": "text", "text": {"content": h}}] for h in headers]
            }
        }
        table_block["table"]["children"].append(header_row)
        
        # Add data rows (skip separator row at index 1)
        for row in rows[2:]:
            cells = [cell.strip() for cell in row.split('|')[1:-1]]
            if len(cells) == len(headers):  # Ensure row has correct number of cells
                data_row = {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [self._parse_inline_formatting(cell) for cell in cells]
                    }
                }
                table_block["table"]["children"].append(data_row)
        
        blocks.append(table_block)
        return blocks
    
    def _is_numbered_risk_item(self, line: str) -> bool:
        """Check if line is a numbered risk item with em dash"""
        return bool(re.match(r'^\d+\.\s+[A-Z][^–]+–', line.strip()))
    
    def _process_numbered_risk_item(self, line: str, all_lines: List[str], current_index: int) -> List[Dict]:
        """Process numbered items that span multiple lines"""
        blocks = []
        
        # Extract the number and title
        match = re.match(r'^(\d+)\.\s+([^–]+)–\s*(.+)', line.strip())
        if match:
            number = match.group(1)
            title = match.group(2).strip()
            content = match.group(3).strip()
            
            # Create a heading for the numbered item
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": f"{number}. {title}"}
                    }]
                }
            })
            
            # Collect all continuation lines
            full_content = [content]
            i = current_index + 1
            while i < len(all_lines) and not self._starts_new_item(all_lines[i]):
                if all_lines[i].strip():
                    full_content.append(all_lines[i].strip())
                i += 1
            
            # Add the content as a paragraph
            if full_content:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": self._parse_inline_formatting(' '.join(full_content))
                    }
                })
        
        return blocks
    
    def _starts_new_item(self, line: str) -> bool:
        """Check if a line starts a new numbered item or section"""
        return bool(re.match(r'^\d+\.\s+', line.strip()) or 
                   line.startswith('#') or 
                   self._is_table_row(line))
    
    def _is_section_header(self, content: str) -> bool:
        """Determine if content is likely a section header"""
        # Section headers typically have multiple words starting with capitals
        words = content.split()
        if len(words) < 2:
            return False
        
        # Check for patterns like "Project Overview", "Technology & Products"
        capital_words = sum(1 for word in words if word and word[0].isupper())
        special_words = sum(1 for word in words if word in ['&', 'and', 'of', 'the', '/', 'or'])
        
        return capital_words + special_words >= len(words) * 0.6
    
    def _parse_inline_formatting(self, text: str) -> List[Dict]:
        """Parse inline markdown formatting and convert URLs/handles to links"""
        # If text is empty, return empty text block
        if not text:
            return [{"type": "text", "text": {"content": ""}}]
        
        # Handle citations in two formats:
        # 1. NEW FORMAT: 【[text](URL)】 - markdown link wrapped in brackets
        # 2. OLD FORMAT: 【text URL】 - for backward compatibility
        
        def clean_link_text(text):
            """Remove trailing punctuation from link text"""
            text = text.strip()
            # Remove trailing colons, dashes, etc.
            text = re.sub(r'[\s—–\-:]+$', '', text)
            return text.strip()
        
        # First, handle NEW format: 【[text](URL)】
        # Simply remove the wrapper brackets since it's already a markdown link
        text = re.sub(
            r'【\[([^\]]+)\]\(([^\)]+)\)】',
            r'[\1](\2)',
            text
        )
        
        # Then handle OLD format: 【text URL】 (for backward compatibility)
        text = re.sub(
            r'【([^】]*?)\s*(https?://[^\s】]+)】',
            lambda m: f'[{clean_link_text(m.group(1))}]({m.group(2)})' if m.group(1).strip() else f'[Link]({m.group(2)})',
            text
        )
        
        # Cleanup pattern: Remove any remaining 【】 brackets (citations without URLs)
        text = re.sub(
            r'【([^】]+)】',
            r'[\1]',
            text
        )
        
        # Clean up any double brackets that might result
        text = re.sub(r'\[\[([^\]]+)\]\]', r'[\1]', text)
        
        result = []
        
        # Combined pattern to match various elements
        pattern = re.compile(
            r'(\*\*\*(.+?)\*\*\*)|'  # Bold+Italic
            r'(\*\*(.+?)\*\*)|'      # Bold
            r'(\*(.+?)\*)|'          # Italic
            r'(`(.+?)`)|'            # Code
            r'(@\w+)|'               # Twitter handles
            r'(\[(.+?)\]\((.+?)\))|' # Markdown links [text](url)
            r'(https?://[^\s\)]+)|'  # URLs
            r'\((https?://[^\s\)]+)\)' # URLs in parentheses
        )
        
        last_end = 0
        
        for match in pattern.finditer(text):
            start, end = match.span()
            
            # Add any plain text before this match
            if start > last_end:
                plain_text = text[last_end:start]
                if plain_text:
                    self._add_text_with_splitting(result, plain_text)
            
            # Process the matched element
            if match.group(1):  # Bold+Italic
                self._add_text_with_splitting(result, match.group(2), 
                                              annotations={"bold": True, "italic": True})
            elif match.group(3):  # Bold
                self._add_text_with_splitting(result, match.group(4), 
                                              annotations={"bold": True})
            elif match.group(5):  # Italic
                self._add_text_with_splitting(result, match.group(6), 
                                              annotations={"italic": True})
            elif match.group(7):  # Code
                self._add_text_with_splitting(result, match.group(8), 
                                              annotations={"code": True})
            elif match.group(9):  # Twitter handle
                handle = match.group(9)
                result.append({
                    "type": "text",
                    "text": {
                        "content": handle,
                        "link": {"url": f"https://twitter.com/{handle[1:]}"}
                    },
                    "annotations": {"color": "blue"}
                })
            elif match.group(10):  # Markdown link [text](url)
                link_text = match.group(11)
                link_url = match.group(12)
                result.append({
                    "type": "text",
                    "text": {
                        "content": link_text,
                        "link": {"url": link_url}
                    },
                    "annotations": {"color": "blue"}
                })
            elif match.group(13):  # Standalone URL
                url = match.group(13)
                # For readability, show domain for long URLs
                display_text = self._get_display_url(url)
                result.append({
                    "type": "text",
                    "text": {
                        "content": display_text,
                        "link": {"url": url}
                    },
                    "annotations": {"color": "blue"}
                })
            elif match.group(14):  # URL in parentheses
                url = match.group(14)
                # Add the opening parenthesis
                result.append({
                    "type": "text",
                    "text": {"content": "("}
                })
                # Add the URL as a link
                display_text = self._get_display_url(url)
                result.append({
                    "type": "text",
                    "text": {
                        "content": display_text,
                        "link": {"url": url}
                    },
                    "annotations": {"color": "blue"}
                })
                # Add the closing parenthesis
                result.append({
                    "type": "text",
                    "text": {"content": ")"}
                })
            
            last_end = end
        
        # Add any remaining plain text
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                self._add_text_with_splitting(result, remaining)
        
        # If no formatting was found, return plain text with splitting
        if not result:
            self._add_text_with_splitting(result, text)
        
        return result
    
    def _get_display_url(self, url: str) -> str:
        """Get a display-friendly version of a URL"""
        # Remove protocol
        display = re.sub(r'^https?://', '', url)
        # Remove www
        display = re.sub(r'^www\.', '', display)
        # Truncate if too long
        if len(display) > 50:
            display = display[:47] + "..."
        return display
    
    def _add_text_with_splitting(self, result: List[Dict], text: str, annotations: Dict = None):
        """Add text to result list, splitting if it exceeds Notion's 2000 char limit"""
        max_length = 1900  # Leave some buffer below 2000 limit
        
        if len(text) <= max_length:
            # Text is within limit, add as-is
            text_block = {
                "type": "text",
                "text": {"content": text}
            }
            if annotations:
                text_block["annotations"] = annotations
            result.append(text_block)
        else:
            # Split text into chunks
            for i in range(0, len(text), max_length):
                chunk = text[i:i + max_length]
                text_block = {
                    "type": "text",
                    "text": {"content": chunk}
                }
                if annotations:
                    text_block["annotations"] = annotations
                result.append(text_block)
    
    def _extract_priority(self, research_content: str) -> str:
        """Extract priority from research content, defaulting to 'Error' if not found"""
        try:
            # First try to extract from META_PRIORITY format
            meta_match = re.search(r'META_PRIORITY:\s*(High|Medium|Low)', research_content, re.IGNORECASE)
            if meta_match:
                priority = meta_match.group(1).capitalize()
                logger.info(f"Found priority from META format: {priority}")
                return priority
            
            # Fallback to old format
            priority_match = re.search(r'Priority\s*:\s*(High|Medium|Low)', research_content, re.IGNORECASE)
            if priority_match:
                priority = priority_match.group(1).capitalize()
                logger.info(f"Found priority: {priority}")
                return priority
            
            # Check if it's an error report
            if "# Research Error Report" in research_content or "# Partial Research Results" in research_content:
                logger.warning("Research content is an error report, setting priority to Error")
                return "Error"
            
            # Default to Error if no priority found
            logger.warning("Could not extract priority from research content, defaulting to Error")
            return "Error"
            
        except Exception as e:
            logger.error(f"Error extracting priority: {e}")
            return "Error"
    
    def _extract_stage(self, research_content: str) -> Optional[str]:
        """Extract stage from research content with fuzzy matching"""
        try:
            # First try to extract from META_STAGE format
            meta_match = re.search(r'META_STAGE:\s*([^\n]+)', research_content, re.IGNORECASE)
            if meta_match:
                raw_stage = meta_match.group(1).strip()
                normalized_stage = self._normalize_stage(raw_stage)
                if normalized_stage:
                    logger.info(f"Found stage from META format: '{raw_stage}' → '{normalized_stage}'")
                    return normalized_stage
                else:
                    logger.warning(f"Could not normalize stage value: '{raw_stage}'")
            
            # Fallback to old format if exists
            stage_match = re.search(r'Stage\s*:\s*([^\n]+)', research_content, re.IGNORECASE)
            if stage_match:
                raw_stage = stage_match.group(1).strip()
                normalized_stage = self._normalize_stage(raw_stage)
                if normalized_stage:
                    logger.info(f"Found stage from old format: '{raw_stage}' → '{normalized_stage}'")
                    return normalized_stage
            
            # No stage found
            logger.info("No stage information found in research content")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting stage: {e}")
            return None

    def _extract_categories(self, research_content: str) -> List[str]:
        """Extract category tags from research content, defaulting to ['Unknown'] if not found."""
        try:
            match = re.search(
                r"^META_CATEGORIES:\s*(.+)$",
                research_content,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if not match:
                match = re.search(
                    r"^META_CATEGORY:\s*(.+)$",
                    research_content,
                    flags=re.IGNORECASE | re.MULTILINE,
                )

            if not match:
                logger.info("No category metadata found (META_CATEGORIES); defaulting to Unknown")
                return ["Unknown"]

            raw_value = match.group(1).strip()
            categories = self._parse_categories_value(raw_value)
            if categories:
                logger.info("Extracted categories: %s", ", ".join(categories))
                return categories

            logger.info("Category metadata present but empty; defaulting to Unknown")
            return ["Unknown"]
        except Exception as exc:
            logger.error("Error extracting categories: %s", exc)
            return ["Unknown"]

    def _extract_monitor_flag(self, research_content: str) -> Optional[bool]:
        """Extract META_MONITOR from research content.

        Returns:
            True if META_MONITOR: Yes
            False if META_MONITOR: No
            None if not present
        """
        try:
            match = re.search(
                r"^META_MONITOR:\s*(Yes|No)\b",
                research_content or "",
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if not match:
                return None
            return match.group(1).strip().lower() == "yes"
        except Exception as exc:
            logger.error("Error extracting monitor flag: %s", exc)
            return None

    def _parse_categories_value(self, raw_value: str) -> List[str]:
        """Parse a META_CATEGORIES value into a list of 1–6 unique category strings."""
        value = (raw_value or "").strip()
        if not value:
            return []

        items: List[str] = []
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    items = [str(item) for item in parsed]
                else:
                    items = [str(parsed)]
            except Exception:
                inner = value.lstrip("[").rstrip("]").strip()
                items = re.split(r"\s*[;,]\s*", inner) if inner else []
        else:
            items = re.split(r"\s*[;,]\s*", value)

        categories: List[str] = []
        seen = set()
        for item in items:
            cleaned = str(item).strip().strip('"').strip("'").strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            categories.append(cleaned)
            if len(categories) >= 6:
                break

        return categories
    
    def _normalize_stage(self, raw_stage: str) -> Optional[str]:
        """Normalize stage value to match Notion's select options with improved fuzzy matching"""
        if not raw_stage:
            return None
            
        # Clean the input - remove parenthetical content and normalize
        stage_lower = raw_stage.strip().lower()
        # Remove parenthetical content like "(pre-product)", "(stealth)", etc.
        stage_clean = re.sub(r'\s*\([^)]*\)', '', stage_lower).strip()
        
        logger.debug(f"Stage normalization: '{raw_stage}' → '{stage_clean}'")
        
        # Exact matches (case-insensitive) - try both original and cleaned versions
        exact_mappings = {
            'pre-seed/seed': 'Pre-Seed/Seed',
            'seed funded': 'Seed Funded',
            'later stage': 'Later Stage',
            'out of scope': 'Out of Scope',
            'out-of-scope': 'Out of Scope',
            'out_of_scope': 'Out of Scope',
            # Add more exact mappings
            'pre-seed': 'Pre-Seed/Seed',
            'preseed': 'Pre-Seed/Seed',
            'seed': 'Seed Funded',
            'seed stage': 'Seed Funded',
            'seed round': 'Seed Funded'
        }
        
        # Try exact match with cleaned version first
        if stage_clean in exact_mappings:
            logger.debug(f"Exact match found: '{stage_clean}' → '{exact_mappings[stage_clean]}'")
            return exact_mappings[stage_clean]
        
        # Try exact match with original
        if stage_lower in exact_mappings:
            logger.debug(f"Exact match found: '{stage_lower}' → '{exact_mappings[stage_lower]}'")
            return exact_mappings[stage_lower]
        
        # Smart fuzzy matching - prioritize most specific matches first

        # 0. Explicit out-of-scope marker (must come before other checks)
        if 'out' in stage_clean and 'scope' in stage_clean:
            logger.debug(f"Out of scope match found for: '{stage_clean}'")
            return 'Out of Scope'
        
        # 1. Pre-seed variations (must come before general seed check)
        pre_seed_terms = ['pre-seed', 'preseed', 'pre seed', 'angel', 'friends', 'family', 'bootstrap']
        if any(term in stage_clean for term in pre_seed_terms):
            logger.debug(f"Pre-seed match found for: '{stage_clean}'")
            return 'Pre-Seed/Seed'
        
        # 2. Seed funded variations (now safe to check for 'seed')
        # Handle special case: "seed funded (pre-product)" should map to "Seed Funded"
        seed_terms = ['seed funded', 'seed stage', 'seed round']
        if any(term in stage_clean for term in seed_terms):
            logger.debug(f"Seed funded match found for: '{stage_clean}'")
            return 'Seed Funded'
        
        # 3. General seed check (but exclude if it's clearly pre-seed context)
        if 'seed' in stage_clean:
            # Check if it's in a pre-seed context by looking at surrounding words
            # But allow "seed funded (pre-product)" to pass through as Seed Funded
            words = stage_clean.split()
            seed_index = next((i for i, word in enumerate(words) if 'seed' in word), -1)
            
            # If 'seed' is preceded by 'pre', it's pre-seed
            if seed_index > 0 and any(words[seed_index-1].startswith(pre) for pre in ['pre', 'pre-']):
                logger.debug(f"Pre-seed context detected for: '{stage_clean}'")
                return 'Pre-Seed/Seed'
            else:
                logger.debug(f"General seed match found for: '{stage_clean}'")
                return 'Seed Funded'
        
        # 4. Later stage indicators
        later_stage_terms = ['later', 'late', 'series', 'post-seed', 'growth', 'expansion', 'scale']
        if any(term in stage_clean for term in later_stage_terms):
            logger.debug(f"Later stage match found for: '{stage_clean}'")
            return 'Later Stage'
        
        # 5. Check for specific series mentions
        if re.search(r'series\s*[a-z]', stage_clean, re.IGNORECASE):
            logger.debug(f"Series funding detected for: '{stage_clean}'")
            return 'Later Stage'
        
        # 6. Revenue/growth stage indicators
        revenue_terms = ['revenue', 'profitable', 'established', 'mature']
        if any(term in stage_clean for term in revenue_terms):
            logger.debug(f"Revenue stage match found for: '{stage_clean}'")
            return 'Later Stage'
        
        # If we can't match, return None (don't guess)
        logger.warning(f"Could not map stage '{raw_stage}' to a valid option (cleaned: '{stage_clean}')")
        return None
    
    def _extract_summary(self, research_content: str) -> str:
        """Extract a summary from the research content"""
        lines = research_content.split('\n')
        summary_lines = []
        in_overview = False
        
        for line in lines:
            if line.strip().startswith('# Project Overview'):
                in_overview = True
                continue
            elif line.strip().startswith('#') and in_overview:
                # End of overview section
                break
            elif in_overview and line.strip():
                summary_lines.append(line.strip())
        
        # Return first 2-3 sentences as summary
        summary = ' '.join(summary_lines)
        if len(summary) > 500:
            # Find a good break point
            sentences = summary.split('. ')
            summary = '. '.join(sentences[:3]) + '.'
        
        return summary
    
    def _update_external_database(
        self,
        project_name: str,
        priority: str,
        stage: Optional[str],
        categories: Optional[List[str]],
        research_content: str,
        score_updates: Optional[Dict[str, Dict]] = None,
        monitor_flag: Optional[bool] = None,
    ):
        """
        Update a page in an external database with the same title.
        This is done after the main update is complete.
        
        Args:
            project_name: The project name to search for
            priority: Already extracted priority
            stage: Already extracted stage (optional)
            categories: Project category tags (optional)
            research_content: The full research report in markdown format
        """
        try:
            # Check if external database ID is configured
            external_db_id = os.environ.get("NOTION_DATABASE_ID_EXT")
            if not external_db_id:
                logger.debug("NOTION_DATABASE_ID_EXT not configured, skipping external update")
                return
            
            logger.info(f"Attempting to update external database for project: {project_name}")
            
            # Step 1: Query the external database to find page with matching title
            query_body = {
                "filter": {
                    "property": "Name",  # Common title property name
                    "title": {
                        "equals": project_name
                    }
                },
                "sorts": [{"timestamp": "created_time", "direction": "descending"}],
                "page_size": 1,
            }
            
            # Try common title property names if "Name" doesn't work
            title_property_names = ["Name", "Title", "Project", "Project Name"]
            found_page = None
            
            for prop_name in title_property_names:
                try:
                    query_body["filter"]["property"] = prop_name
                    response = self.notion.databases.query(
                        database_id=external_db_id,
                        **query_body
                    )
                    
                    if response.get("results"):
                        found_page = response["results"][0]
                        logger.info(f"Found matching page in external database using property '{prop_name}'")
                        break
                except Exception as e:
                    logger.debug(f"Property '{prop_name}' not found or query failed: {e}")
                    continue
            
            if not found_page:
                logger.warning(f"No page found in external database with title: {project_name}")
                return
            
            external_page_id = found_page["id"]
            logger.info(f"Found external page ID: {external_page_id}")
            
            # Step 2: Update the external page properties
            target_status = "monitor" if monitor_flag is True else "completed"
            update_properties = {
                "Research Status": {
                    "multi_select": [{"name": target_status}]
                },
                "Ava's Priority": {
                    "select": {"name": priority}
                }
            }

            # Add stage if available
            if stage:
                update_properties["Stage"] = {
                    "select": {"name": stage}
                }

            category_list = [c for c in (categories or []) if c and str(c).strip()]
            if not category_list:
                category_list = ["Unknown"]
            update_properties["Category"] = {
                "multi_select": [{"name": str(cat).strip()} for cat in category_list]
            }

            if score_updates:
                update_properties.update(score_updates)
            
            # Try to update properties - may fail if property names don't match
            try:
                self.notion.pages.update(
                    page_id=external_page_id,
                    properties=update_properties
                )
                logger.info(f"Updated properties in external database for {project_name}")
                if stage:
                    logger.info(f"Set Stage to '{stage}' in external database")
            except Exception as e:
                logger.warning(f"Failed to update properties in external database: {e}")
                # Retry without missing properties if they were the issue
                error_str = str(e)
                if stage and "Stage" in error_str:
                    logger.info("Retrying external database update without stage...")
                    update_properties.pop("Stage", None)
                if "Category" in error_str:
                    logger.info("Retrying external database update without Category...")
                    update_properties.pop("Category", None)
                try:
                    self.notion.pages.update(
                        page_id=external_page_id,
                        properties=update_properties
                    )
                    logger.info("Updated properties (after retry) in external database")
                except Exception:
                    pass
                # Continue anyway to append content
            
            # Step 3: Append the same report content to the external page
            try:
                self._append_research_content_to_page(external_page_id, research_content)
                logger.info(f"Successfully appended research content to external database for {project_name}")
            except Exception as e:
                logger.error(f"Failed to append content to external database: {e}")
            
        except Exception as e:
            # Log error but don't interrupt the main workflow
            logger.error(f"Error updating external database for {project_name}: {e}")
            # Don't raise - this is a non-critical operation
    
    def _create_reasoning_child_page(self, parent_page_id: str, project_name: str, project_dir: str) -> Optional[str]:
        """
        Create a child page under the main research page containing the reasoning content.
        
        Args:
            parent_page_id: The ID of the parent page
            project_name: Name of the project (for logging)
            project_dir: Path to the project directory containing reasoning file
            
        Returns:
            The URL of the created child page, or None if creation failed
        """
        try:
            # Check if reasoning file exists
            reasoning_file_path = os.path.join(project_dir, '02_reasoning.md')
            if not os.path.exists(reasoning_file_path):
                logger.info(f"No reasoning file found at {reasoning_file_path}, skipping child page creation")
                return None
            
            # Read the reasoning content
            with open(reasoning_file_path, 'r', encoding='utf-8') as f:
                reasoning_content = f.read()
            
            if not reasoning_content.strip():
                logger.info("Reasoning file is empty, skipping child page creation")
                return None
            
            logger.info(f"Creating reasoning child page for {project_name}")
            
            # Create the child page with reasoning content
            # Split content into paragraphs (Notion has limits on block size)
            blocks = []
            
            # Add a header
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "🧠 AI Reasoning Process"}
                    }]
                }
            })
            
            # Add a callout with context
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": f"This page contains Ava's reasoning process during research for {project_name}. Generated: {self._get_eastern_time()}"
                        }
                    }],
                    "icon": {"emoji": "💭"},
                    "color": "purple_background"
                }
            })
            
            # Add a divider
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Process reasoning content - split into chunks to avoid Notion limits
            # Split by double newlines to preserve paragraph structure
            paragraphs = reasoning_content.split('\n\n')
            
            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue
                
                # Split very long paragraphs into smaller chunks (Notion limit is ~2000 chars per text block)
                max_chunk_size = 1900
                if len(paragraph) > max_chunk_size:
                    # Split at sentence boundaries if possible
                    sentences = paragraph.replace('. ', '.SPLIT').split('SPLIT')
                    current_chunk = ""
                    
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 1 < max_chunk_size:
                            current_chunk += sentence + " " if not sentence.endswith('.') else sentence
                        else:
                            if current_chunk:
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [{
                                            "type": "text",
                                            "text": {"content": current_chunk.strip()}
                                        }]
                                    }
                                })
                            current_chunk = sentence
                    
                    # Add any remaining chunk
                    if current_chunk:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{
                                    "type": "text",
                                    "text": {"content": current_chunk.strip()}
                                }]
                            }
                        })
                else:
                    # Add as a single paragraph block
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": paragraph.strip()}
                            }]
                        }
                    })
            
            # Create the child page
            try:
                response = self.notion.pages.create(
                    parent={"page_id": parent_page_id},
                    properties={
                        "title": {
                            "title": [{
                                "text": {"content": "🧠 Reasoning"}
                            }]
                        }
                    },
                    children=blocks[:100]  # Notion limits initial children to 100 blocks
                )
                
                child_page_id = response.get('id')
                child_page_url = response.get('url', '')
                
                # If there are more than 100 blocks, append the rest
                if len(blocks) > 100:
                    logger.info(f"Appending additional {len(blocks) - 100} blocks to reasoning page")
                    for i in range(100, len(blocks), 50):  # Append in batches of 50
                        batch = blocks[i:i + 50]
                        try:
                            self.notion.blocks.children.append(
                                block_id=child_page_id,
                                children=batch
                            )
                        except Exception as e:
                            logger.warning(f"Failed to append reasoning blocks batch {i//50}: {e}")
                            # Continue with other batches even if one fails
                
                logger.info(f"Successfully created reasoning child page: {child_page_url}")
                return child_page_url
                
            except Exception as e:
                logger.error(f"Failed to create reasoning child page: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error in _create_reasoning_child_page: {e}")
            return None
    
