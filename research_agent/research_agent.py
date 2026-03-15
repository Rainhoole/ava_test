import os
import logging
import argparse
import re
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import warnings

# Suppress Pydantic serialization warnings globally
warnings.filterwarnings("ignore", category=UserWarning, message=".*Pydantic.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*serializ.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*unexpected.*")

# Clear proxy vars (copied from api_test.py)
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from openai import OpenAI
from notion_client import Client
from dotenv import load_dotenv
from notion_updater import NotionUpdater
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue

# Import streaming modules (required)
from streaming_processor import StreamingProcessor

# Load environment
load_dotenv('../reference_project/twitter-vc-analyzer-master/.env')
load_dotenv('../.env')  # Also load main .env

# Logging setup with session directories
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# Create daily directory (one per day, not per session)
daily_timestamp = datetime.now().strftime("%Y%m%d")
session_dir = os.path.join(log_dir, f'projects_{daily_timestamp}')
os.makedirs(session_dir, exist_ok=True)

# Console log file with timestamp (multiple runs per day)
console_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
main_log_file = os.path.join(session_dir, f'console_output_{console_timestamp}.log')

# Configure main logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(main_log_file, mode='w', encoding='utf-8'),
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)
# Silence noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)

# Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")

# Load system prompt from external file
def load_system_prompt(prompt_file_path=None):
    """Load the system prompt from specified file or default research_agent_prompt_al.md
    
    Args:
        prompt_file_path: Optional path to custom prompt file. If None, uses default.
    """
    if prompt_file_path:
        # Use custom prompt file
        prompt_file = prompt_file_path
    else:
        # Use default prompt file
        prompt_file = os.path.join(os.path.dirname(__file__), 'research_agent_prompt_al.md')
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.info(f"Loaded system prompt from: {prompt_file}")
            return content
    except FileNotFoundError:
        logger.error(f"System prompt file not found: {prompt_file}")
        raise
    except Exception as e:
        logger.error(f"Error loading system prompt: {e}")
        raise

# Default system message - will be overridden if custom prompt is specified
SYSTEM_MESSAGE = None

class ResearchAgent:
    def __init__(self, use_flex=True, model: str = None, system_message=None):
        # Store API key instead of client instance - each worker will create its own
        self.openai_api_key = OPENAI_API_KEY
        self.notion = Client(auth=NOTION_API_KEY)
        self.database_id = NOTION_DATABASE_ID
        self.notion_updater = NotionUpdater(self.notion, self.database_id)
        self._lock = threading.Lock()  # For thread-safe operations
        self.use_flex = use_flex  # Whether to use flex processing for cost savings (default: True)
        self.model = model  # Model to use for research (required)
        self.system_message = system_message or SYSTEM_MESSAGE  # System prompt to use
        self.error_500_count = 0  # Track 500/424 errors across the run
        self.max_500_errors = 5  # Maximum 500/424 errors before terminating
        self.should_terminate = False  # Flag to signal early termination
        self.session_dir = session_dir  # Session directory for organized logging
        
    def get_unresearched_projects(self, limit: int = 5, require_twitter: bool = True) -> List[Dict]:
        """Query Notion for projects that are not researched (empty, 'not researched', 'error' status, or stuck 'in progress')
        
        Args:
            limit: Maximum number of projects to return
            require_twitter: If True, only return projects with Twitter handles
        """
        all_results = []
        
        # Query for all unresearched projects using OR filter
        # Sort newest by Date first (fallback to created_time)
        response = self.notion.databases.query(
            database_id=self.database_id,
            filter={
                "or": [
                    {
                        "property": "Research Status",
                        "multi_select": {"is_empty": True}
                    },
                    {
                        "property": "Research Status",
                        "multi_select": {"contains": "not researched"}
                    },
                    {
                        "property": "Research Status",
                        "multi_select": {"contains": "error"}
                    },
                    {
                        "property": "Research Status",
                        "multi_select": {"contains": "in progress"}
                    }
                ]
            },
            sorts=[
                {"property": "Date", "direction": "descending"},
                {"timestamp": "created_time", "direction": "descending"},
            ],
            page_size=limit * 3 if require_twitter else limit * 2  # Get extra to account for filtering
        )
        
        results = response.get('results', [])
        logger.info(f"Queried Notion database: retrieved {len(results)} unresearched projects (limit was {limit}, page_size was {limit * 3 if require_twitter else limit * 2})")
        
        # Log details of each retrieved project
        for i, project in enumerate(results):
            project_info = self.extract_project_info(project)
            logger.info(f"  Project {i+1}: '{project_info['name']}'")
            logger.info(f"    ID: {project_info['id']}")
            logger.info(f"    Research Status: {project_info.get('research_status', [])}")
            logger.info(f"    Twitter Handles: {project_info.get('twitter_handles', [])}")
            logger.info(f"    Summary: {project_info.get('summary', 'N/A')[:100]}...")
        
        def _get_notion_date_sort_key(page: Dict) -> str:
            date_prop = (page.get("properties", {}) or {}).get("Date", {}) or {}
            date_info = date_prop.get("date") or {}
            start = date_info.get("start") or ""
            return start or page.get("created_time", "") or ""

        # Sort results by Date (newest first) to mirror Notion query
        try:
            results.sort(key=_get_notion_date_sort_key, reverse=True)
            logger.info(f"Sorted {len(results)} projects by Date (newest first)")
        except Exception as e:
            logger.debug(f"Error sorting by date: {e}")
        
        # Process results to filter out non-stuck "in progress" projects
        current_time = datetime.now()
        for project in results:
            project_info = self.extract_project_info(project)
            research_status = project_info.get('research_status', [])
            
            logger.debug(f"Processing project '{project_info['name']}' with status: {research_status}")
            
            # If it's "in progress", check if it's stuck
            if 'in progress' in research_status:
                last_edited = project.get('last_edited_time', '')
                if last_edited:
                    try:
                        # Parse ISO format datetime
                        last_edited_time = datetime.fromisoformat(last_edited.replace('Z', '+00:00'))
                        # Convert to naive datetime for comparison
                        last_edited_time = last_edited_time.replace(tzinfo=None)
                        time_diff = current_time - last_edited_time
                        hours_ago = time_diff.total_seconds() / 3600
                        
                        logger.debug(f"'{project_info['name']}' last edited {hours_ago:.1f} hours ago")
                        
                        # If more than 2 hours old, consider it stuck
                        if time_diff.total_seconds() > 7200:  # 2 hours in seconds
                            logger.warning(f"Found stuck 'in progress' project: {project_info['name']} (last edited: {hours_ago:.1f} hours ago)")
                            all_results.append(project)
                        else:
                            logger.info(f"Skipping recent 'in progress' project: {project_info['name']} (last edited: {hours_ago:.1f} hours ago, not stuck)")
                    except Exception as e:
                        logger.debug(f"Error parsing datetime for project '{project_info['name']}': {e}")
                        # If we can't parse datetime, include it as potentially stuck
                        logger.warning(f"Including 'in progress' project with unparseable date: {project_info['name']}")
                        all_results.append(project)
                else:
                    # No last edited time, assume it might be stuck
                    logger.warning(f"Including 'in progress' project with no last_edited_time: {project_info['name']}")
                    all_results.append(project)
            else:
                # Not "in progress", include it
                if 'error' in research_status:
                    logger.info(f"Found project with error status: {project_info['name']}")
                elif not research_status or 'not researched' in research_status:
                    logger.info(f"Found unresearched project: {project_info['name']}")
                all_results.append(project)
            
        logger.info(f"After filtering stuck/unresearched projects: {len(all_results)} projects remain")
        
        # Filter projects with Twitter handles if required
        if require_twitter:
            logger.info(f"Filtering {len(all_results)} projects for Twitter handles (require_twitter=True)")
            filtered_results = []
            for i, project in enumerate(all_results):
                project_info = self.extract_project_info(project)
                handles = project_info.get('twitter_handles', [])
                
                logger.info(f"  Checking project {i+1}: '{project_info['name']}'")
                logger.info(f"    Twitter handles: {handles}")
                logger.info(f"    Has handles: {bool(handles)}")
                if handles:
                    logger.info(f"    First handle non-empty: {bool(handles[0])}")
                
                if handles and handles[0]:
                    filtered_results.append(project)
                    logger.info(f"    ✓ ACCEPTED: Project has valid Twitter handle")
                else:
                    logger.info(f"    ✗ REJECTED: Project missing Twitter handle")
                
                if len(filtered_results) >= limit:
                    logger.info(f"  Reached limit of {limit} projects, stopping filter")
                    break
            
            logger.info(f"Filtering complete: {len(filtered_results)} projects with Twitter handles (from {len(all_results)} total)")
            return filtered_results[:limit]
        else:
            logger.info(f"No Twitter filtering required (require_twitter=False), returning {len(all_results)} projects")
        
        return all_results[:limit]
    
    def get_project_directory(self, project_info: Dict) -> str:
        """Get the project directory path using handle-only naming
        
        This ensures consistency with StreamingProcessor directory creation.
        Always returns handle-only directory path.
        """
        # Get Twitter handle for directory naming
        if project_info.get('twitter_handles') and project_info['twitter_handles']:
            twitter_handle = project_info['twitter_handles'][0].replace('@', '')
            # Sanitize for filesystem - same as StreamingProcessor
            safe_handle = re.sub(r'[^\w]', '', twitter_handle)
            return os.path.join(self.session_dir, safe_handle)
        else:
            # Fallback to sanitized project name if no handle (shouldn't happen)
            safe_name = re.sub(r'[^\w\s-]', '', project_info.get('name', 'unknown')).strip()
            safe_name = re.sub(r'[-\s]+', '-', safe_name)
            return os.path.join(self.session_dir, safe_name)
    
    def extract_project_info(self, project: Dict) -> Dict:
        """Extract key information from Notion project"""
        props = project.get('properties', {})
        
        # Extract text properties
        name = self._get_text_property(props.get('Name', {}))
        twitter_raw = self._get_text_property(props.get('Twitter', {}))
        summary = self._get_text_property(props.get('Summary', {}))
        
        # Extract research status
        research_status = []
        status_prop = props.get('Research Status', {})
        if status_prop.get('multi_select'):
            research_status = [item.get('name', '') for item in status_prop['multi_select']]
        
        # Debug logging for Twitter extraction
        logger.debug(f"[{name}] Raw Twitter property: '{twitter_raw}'")
        
        # Clean Twitter handle
        twitter = twitter_raw
        if twitter:
            original_twitter = twitter
            twitter = twitter.strip()
            logger.debug(f"[{name}] After strip: '{twitter}'")
            
            twitter = re.sub(r'https?://[^\s]+', '', twitter)
            logger.debug(f"[{name}] After URL removal: '{twitter}'")
            
            twitter = twitter.replace('@', '').strip()
            logger.debug(f"[{name}] After @ removal and strip: '{twitter}'")
            
            if twitter != original_twitter:
                logger.debug(f"[{name}] Twitter handle cleaned: '{original_twitter}' -> '{twitter}'")
        else:
            logger.debug(f"[{name}] No Twitter property found or empty")
        
        final_handles = [twitter] if twitter else []
        logger.debug(f"[{name}] Final twitter_handles: {final_handles}")
        
        return {
            'id': project['id'],
            'name': name,
            'twitter_handles': final_handles,
            'summary': summary,
            'research_status': research_status
        }
    
    def research_project(self, project_info: Dict, project_logger: logging.Logger = None, override_research: bool = False, position: int = None, total: int = None) -> Optional[str]:
        """Execute research on a single project
        
        Args:
            project_info: Project information dictionary
            project_logger: Logger instance for project-specific logging
            override_research: If True, override early exit rules for later-stage projects
            position: Current position in batch (for progress tracking)
            total: Total number of projects in batch (for progress tracking)
        """
        # Use project logger if provided, otherwise use main logger
        log = project_logger or logger
        
        # Check early termination flag before starting
        if self.should_terminate:
            log.warning("Research cancelled due to early termination flag")
            return None
        
        # Validate Twitter handle exists and is not empty
        if not project_info.get('twitter_handles') or not project_info['twitter_handles'][0]:
            log.error(f"No Twitter handle provided for project: {project_info['name']}")
            logger.error(f"Skipping research for {project_info['name']} - no Twitter handle")
            
            # Return an error report instead of calling AI
            return f"""# Research Error Report

## Error Details
- **Project**: {project_info['name']}
- **Error Type**: MissingTwitterHandle
- **Error Message**: No Twitter handle was provided for this project
- **Timestamp**: {datetime.now().isoformat()}

## Required Action
Please add a Twitter handle to this project in Notion before attempting to research it.

## Note
The research agent requires a valid Twitter handle (e.g., @username) to perform analysis.
Without a Twitter handle, the agent cannot gather the necessary social media data.
"""
        
        # Build user query - we know twitter_handles exists and has content at this point
        user_query = f"Research twitter profile {project_info['twitter_handles'][0]}"
        
        # Add override instruction if flag is set
        if override_research:
            user_query += "\n\nIMPORTANT OVERRIDE: You must complete full research even if this is a later-stage project. Do NOT apply the early exit rule for late-stage projects. Provide complete analysis regardless of funding stage."
            log.info("Override flag set - will research even if later-stage project")
        
        log.info(f"Starting research with query: {user_query}")
        logger.info(f"Researching: {user_query} with model {self.model}")  # Also log to main
        
        # Use streaming for all research
        return self._research_with_streaming(project_info, user_query, log, position, total)
    
    def _research_with_streaming(self, project_info: Dict, user_query: str, 
                                 project_logger: logging.Logger, position: int = None, total: int = None) -> Optional[str]:
        """Execute research using streaming responses"""
        twitter_handle = project_info['twitter_handles'][0]
        worker_id = threading.current_thread().name
        
        
        try:
            # Create streaming processor
            processor = StreamingProcessor(
                api_key=self.openai_api_key,
                model=self.model,
                use_flex=self.use_flex,
                session_dir=self.session_dir,
                twitter_handle=twitter_handle,
                project_name=project_info['name'],  # Pass project name for consistent directory naming
                worker_id=worker_id,
                position=position,  # Pass position for progress tracking
                total=total,  # Pass total for progress tracking
                mock_mode=False  # Set to True for testing without API calls
            )
            
            # Process research with streaming
            report = processor.process_research(
                system_message=self.system_message,
                user_query=user_query,
                mcp_server_url=MCP_SERVER_URL,
                max_retries=3 if self.use_flex else 1
            )
            
            if report:
                project_logger.info(f"Streaming research completed: {len(report)} chars")
                return report
            else:
                project_logger.warning("Streaming research returned empty report")
                return None
                
        except Exception as e:
            error_str = str(e)
            
            # Handle 500/424 errors
            if "Error code: 500" in error_str or "Error code: 424" in error_str:
                error_code = "500" if "Error code: 500" in error_str else "424"
                with self._lock:
                    self.error_500_count += 1
                    project_logger.error(f"Got {error_code} error (count: {self.error_500_count}/{self.max_500_errors})")
                    logger.error(f"{error_code} Error #{self.error_500_count} encountered for {project_info['name']} - skipping silently")
                    
                    if self.error_500_count >= self.max_500_errors:
                        self.should_terminate = True
                        project_logger.error(f"CRITICAL: Reached maximum 500/424 errors ({self.max_500_errors}). Terminating all research.")
                        logger.error(f"TERMINATING: Too many 500/424 errors ({self.max_500_errors})")
                
                return None
            
            # Return error report for other errors
            project_logger.error(f"Streaming research failed: {type(e).__name__}: {str(e)}")
            project_logger.exception("Full stack trace:")
            
            # Clean up error message
            if "<!DOCTYPE html>" in error_str:
                if "502" in error_str:
                    error_message = "502 Bad Gateway - OpenAI API infrastructure error"
                elif "503" in error_str:
                    error_message = "503 Service Unavailable - OpenAI API is temporarily down"
                else:
                    error_message = "HTML error page received - API communication error"
            else:
                error_message = str(e)[:500] + "..." if len(str(e)) > 500 else str(e)
            
            return f"""# Research Error Report

## Error Details
- **Project**: {project_info['name']}
- **Error Type**: {type(e).__name__}
- **Error Message**: {error_message}
- **Timestamp**: {datetime.now().isoformat()}

## Recommended Actions
1. Check the logs for detailed error information
2. Verify API keys and server connectivity
3. Contact support if the error persists
"""
    
    def update_research_status(self, page_id: str, status: str):
        """Update the Research Status property of a project"""
        self.notion_updater.update_status(page_id, status)
    
    def update_notion_with_research(self, project_id: str, project_name: str, report_content: str, project_dir: str = None) -> str:
        """Update existing Notion database item with research results"""
        return self.notion_updater.update_item_with_research(project_id, project_name, report_content, project_dir)
    
    def _get_text_property(self, prop: Dict) -> str:
        """Extract text from Notion property"""
        if prop.get('title'):
            return ''.join([t.get('plain_text', '') for t in prop['title']])
        elif prop.get('rich_text'):
            return ''.join([t.get('plain_text', '') for t in prop['rich_text']])
        return ""
    
    def extract_scoring_data(self, report_content: str) -> tuple[int, int, str]:
        """Extract score, denominator, and priority from report
        Returns: (score, denominator, priority) or (-1, denominator, "Error") if not found
        """
        score = -1
        denominator = -1
        priority = "Error"
        
        try:
            # Extract score with flexible patterns - handles both old (X/26) and new (X/100) formats
            score_patterns = [
                r'\*\*Score\s*:\s*(\d+)\s*/\s*(\d+)\*\*',  # Bold format **Score: X/Y**
                r'Score\s*:\s*(\d+)\s*/\s*(\d+)',          # Regular format
                r'Score\s*:\s*(\d+)/(\d+)',                # Compact format
                r'Total.*?:\s*(\d+)\s*/\s*(\d+)',          # Total format
            ]
            
            for pattern in score_patterns:
                match = re.search(pattern, report_content, re.IGNORECASE)
                if match:
                    score = int(match.group(1))
                    denominator = int(match.group(2))
                    break
            
            # If no score found, try to detect what denominator should be used
            # by looking for scoring breakdown patterns
            if denominator == -1:
                # Check for new format indicators (out of 100)
                if any(x in report_content for x in ['(17/25)', '(26/35)', '(24/35)', '/100', 'out of 100']):
                    denominator = 100  # New format detected
                    logger.debug("Detected new scoring format (out of 100)")
                # Check for old format indicators (out of 26)
                elif any(x in report_content for x in ['/26', 'out of 26', 'total: 26']):
                    denominator = 26   # Old format detected
                    logger.debug("Detected old scoring format (out of 26)")
                else:
                    # Default to new format (100) since that's what we're using now
                    denominator = 100
                    logger.debug("No format detected, defaulting to new format (out of 100)")
            
            # Extract priority (trust AI's assessment)
            # Try META format first, then regular format
            # Updated patterns to handle additional context like "Low (Late-stage / outside mandate)"
            priority_patterns = [
                r'META_PRIORITY\s*:\s*(High|Medium|Low)\b',    # META format
                r'\*\*Priority\s*:\s*\*\*\s*(High|Medium|Low)\b', # Bold format
                r'\*\*Priority\s*:\s*(High|Medium|Low)\b',     # Bold format with content
                r'Priority\s*:\s*(High|Medium|Low)\b',         # Regular format
            ]
            
            for pattern in priority_patterns:
                priority_match = re.search(pattern, report_content, re.IGNORECASE)
                if priority_match:
                    priority = priority_match.group(1).capitalize()
                    break
            
            # Log what we found
            if score >= 0:
                logger.debug(f"Extracted: score={score}/{denominator}, priority={priority}")
            else:
                logger.warning(f"No valid score found in report (will use -1/{denominator})")
            
        except Exception as e:
            logger.error(f"Error extracting scoring data: {e}")
            # Default to new format on error
            if denominator == -1:
                denominator = 100
        
        return (score, denominator, priority)

    def extract_monitor_flag(self, report_content: str) -> Optional[bool]:
        """Extract META_MONITOR flag from report content.

        Returns:
            True if META_MONITOR: Yes
            False if META_MONITOR: No
            None if META_MONITOR not found
        """
        if not report_content:
            return None

        match = re.search(
            r"^META_MONITOR\s*:\s*(Yes|No)\b",
            report_content,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not match:
            return None

        return match.group(1).strip().lower() == "yes"
    
    def update_score_in_databases(self, project_id: str, project_name: str, score: int, denominator: int = 100) -> bool:
        """Update Raw Score and Denominator fields in both main and external databases
        Note: Ava's Score (normalized) is calculated automatically by Notion formula
        Returns: True if successful, False otherwise
        """
        success = True
        
        # Ensure we have valid values even if LLM fails
        score = score if score >= -1 else -1
        denominator = denominator if denominator > 0 else 100
        
        # Prepare properties to update
        update_properties = {
            "Raw Score": {
                "number": score
            },
            "Denominator": {
                "number": denominator
            }
        }
        
        # Update main database
        try:
            self.notion.pages.update(
                page_id=project_id,
                properties=update_properties
            )
            logger.info(f"✓ Updated Raw Score and Denominator in main database: {score}/{denominator}")
        except Exception as e:
            logger.error(f"✗ Failed to update score in main database: {e}")
            # Try to update with minimal properties if specific fields don't exist
            try:
                # Fallback: try updating only Raw Score if that's all that exists
                self.notion.pages.update(
                    page_id=project_id,
                    properties={"Raw Score": {"number": score}}
                )
                logger.info(f"✓ Fallback: Updated only Raw Score in main database: {score}")
            except:
                success = False
        
        # Update external database if configured
        external_db_id = os.environ.get("NOTION_DATABASE_ID_EXT")
        if external_db_id:
            try:
                # Find matching entry in external database
                external_entry = self._find_entry_in_external_db(project_name, external_db_id)
                if external_entry:
                    try:
                        self.notion.pages.update(
                            page_id=external_entry['id'],
                            properties=update_properties
                        )
                        logger.info(f"✓ Updated Raw Score and Denominator in external database: {score}/{denominator}")
                    except Exception as e:
                        # Try fallback for external DB too
                        logger.warning(f"Failed full update in external DB: {e}")
                        try:
                            self.notion.pages.update(
                                page_id=external_entry['id'],
                                properties={"Raw Score": {"number": score}}
                            )
                            logger.info(f"✓ Fallback: Updated only Raw Score in external database: {score}")
                        except:
                            logger.error(f"✗ Failed all updates in external database")
                            success = False
                else:
                    logger.warning(f"! No matching entry found in external database for: {project_name}")
                    success = False
            except Exception as e:
                logger.error(f"✗ Failed to update score in external database: {e}")
                success = False
        
        return success
    
    def _find_entry_in_external_db(self, project_name: str, external_db_id: str) -> Optional[Dict]:
        """Find matching entry in external database by name"""
        # Try common title property names
        title_property_names = ["Name", "Title", "Project", "Project Name"]
        
        for prop_name in title_property_names:
            try:
                response = self.notion.databases.query(
                    database_id=external_db_id,
                    filter={
                        "property": prop_name,
                        "title": {
                            "equals": project_name
                        }
                    },
                    page_size=1
                )
                
                if response.get("results"):
                    return response["results"][0]
            except Exception as e:
                logger.debug(f"Property '{prop_name}' not found or query failed: {e}")
                continue
        
        return None
    
    def _log_error_details(self, error: Exception, project_info: Dict, project_logger: logging.Logger = None):
        """Log detailed error information"""
        
        # Always use main log file since we don't have project-specific loggers anymore
        log_file_to_use = main_log_file
            
        error_str = str(error)
        
        with open(log_file_to_use, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"=== ERROR FOR: {project_info['name']} (ID: {project_info['id']}) ===\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            
            # Handle HTML error responses specially
            if "<!DOCTYPE html>" in error_str:
                f.write("Error Message: Received HTML error page\n")
                f.write("\n--- HTML ERROR PAGE CONTENT ---\n")
                f.write(error_str)
                f.write("\n--- END HTML ERROR PAGE ---\n")
                
                # Also save to a separate HTML file for easier viewing
                html_error_file = log_file_to_use.replace('.log', '_error.html')
                with open(html_error_file, 'w', encoding='utf-8') as html_f:
                    html_f.write(error_str)
                f.write(f"Full HTML error saved to: {html_error_file}\n")
            else:
                # For non-HTML errors, log normally but truncate if too long
                if len(error_str) > 2000:
                    f.write(f"Error Message (truncated): {error_str[:2000]}...\n")
                    f.write(f"Full error length: {len(error_str)} characters\n")
                else:
                    f.write(f"Error Message: {error_str}\n")
            
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"{'='*80}\n\n")
    
    def process_single_project(self, project_info: Dict, position: int, total: int, override_research: bool = False) -> Dict[str, Any]:
        """Process a single project and return results. Thread-safe.
        
        Args:
            project_info: Project information dictionary
            position: Position in batch
            total: Total number of projects
            override_research: If True, override early exit rules for later-stage projects
        """
        thread_name = threading.current_thread().name
        
        # Check if we should terminate early
        if self.should_terminate:
            logger.warning(f"[{thread_name}] [{position}/{total}] Skipping project due to too many 500/424 errors")
            return {
                'project_info': project_info,
                'success': False,
                'url': None,
                'error': 'Skipped due to too many 500/424 errors',
                'thread': thread_name
            }
        
        # Log start of research
        logger.info(f"[{thread_name}] [{position}/{total}] Starting research process for {project_info['name']}")
        
        # Also log to main logger for overview
        is_error_retry = 'error' in project_info.get('research_status', [])
        is_stuck_retry = 'in progress' in project_info.get('research_status', [])
        retry_msg = ""
        if is_error_retry:
            retry_msg = " (RETRY - previous error)"
        elif is_stuck_retry:
            retry_msg = " (RETRY - stuck in progress)"
        logger.info(f"[{thread_name}] [{position}/{total}] Starting research for: {project_info['name']}{retry_msg}")
        
        result = {
            'project_info': project_info,
            'success': False,
            'url': None,
            'error': None,
            'thread': thread_name
        }
        
        try:
            # Update status to in progress
            logger.info(f"[{thread_name}] Updating Notion status to 'in progress'")
            self.update_research_status(project_info['id'], "in progress")
            
            # Perform research
            logger.info(f"[{thread_name}] Starting research...")
            report = self.research_project(project_info, project_logger=None, override_research=override_research, position=position, total=total)
            
            if report is None:
                # This is a 500/424 error - don't update Notion, revert status
                logger.error(f"[{thread_name}] Got 500/424 error - skipping Notion update")
                logger.error(f"[{thread_name}] [{position}/{total}] ⚠ 500/424 error - project remains unresearched")
                result['error'] = '500/424 error - skipped'
                # Revert status back to what it was (empty or error) for retry
                original_status = project_info.get('research_status', [])
                if 'error' in original_status:
                    # It was already an error, keep it as error
                    self.update_research_status(project_info['id'], "error")
                else:
                    # It was empty/not researched, remove the "in progress" status
                    # by updating to an empty multi-select
                    try:
                        self.notion.pages.update(
                            page_id=project_info['id'],
                            properties={
                                "Research Status": {
                                    "multi_select": []  # Empty array removes all status tags
                                }
                            }
                        )
                    except:
                        pass  # If it fails, just leave it
            elif report:
                # Check if it's an error report
                is_error = "# Research Error Report" in report or "# Partial Research Results" in report
                
                # Update Notion with research (with better error handling)
                logger.info(f"[{thread_name}] Uploading research report to Notion...")
                try:
                    # Get the project directory where StreamingProcessor writes files
                    project_dir = self.get_project_directory(project_info)
                    logger.debug(f"[{thread_name}] Using project directory: {project_dir}")
                    
                    url = self.update_notion_with_research(
                        project_info['id'],
                        project_info['name'],
                        report,
                        project_dir
                    )
                    
                    # Update status based on result
                    if is_error:
                        logger.error(f"[{thread_name}] Research completed with errors")
                        self.update_research_status(project_info['id'], "error")
                        logger.warning(f"[{thread_name}] [{position}/{total}] ⚠ Research had errors but report uploaded: {url}")
                        result['error'] = 'Research completed with errors'
                    else:
                        meta_monitor = self.extract_monitor_flag(report)
                        if meta_monitor is True:
                            logger.info(f"[{thread_name}] Research completed successfully (META_MONITOR=Yes)")
                            self.update_research_status(project_info['id'], "monitor")
                            logger.info(f"[{thread_name}] [{position}/{total}] ✓ Research complete (monitor): {url}")
                        else:
                            logger.info(f"[{thread_name}] Research completed successfully!")
                            self.update_research_status(project_info['id'], "completed")
                            logger.info(f"[{thread_name}] [{position}/{total}] ✓ Research complete: {url}")
                        result['success'] = True
                    
                    logger.info(f"[{thread_name}] Notion URL: {url}")
                    result['url'] = url
                    
                except Exception as upload_error:
                    # Handle upload failures gracefully
                    logger.error(f"[{thread_name}] Failed to upload report to Notion: {upload_error}")
                    
                    # Save report locally as fallback
                    project_dir = self.get_project_directory(project_info)
                    fallback_file = os.path.join(project_dir, 'upload_failed_report.md')
                    try:
                        with open(fallback_file, 'w', encoding='utf-8') as f:
                            f.write(report)
                        logger.info(f"[{thread_name}] Report saved locally due to upload failure: {fallback_file}")
                        logger.warning(f"[{thread_name}] [{position}/{total}] ⚠ Upload failed but report saved: {fallback_file}")
                    except Exception as save_error:
                        logger.error(f"[{thread_name}] Failed to save report locally: {save_error}")
                    
                    # Mark as error status since upload failed
                    self.update_research_status(project_info['id'], "error")
                    result['error'] = f'Upload failed: {str(upload_error)[:100]}'
                    
                    # Don't re-raise - we've handled it gracefully
                    # The research was successful even if upload failed
                
                # Extract and update score regardless of upload success/error status
                logger.info(f"[{thread_name}] Extracting scoring data from report...")
                score, denominator, priority = self.extract_scoring_data(report)
                
                # Always update score, even if -1 (to indicate no score found)
                if score >= 0 and denominator > 0:
                    logger.info(f"[{thread_name}] Valid scoring: {score}/{denominator}, Priority: {priority}")
                else:
                    logger.warning(f"[{thread_name}] Invalid or missing scoring data (score={score}, denominator={denominator}), will store -1")
                    score = -1
                    # Keep denominator as detected/defaulted by extract_scoring_data
                
                # Update scores in both databases
                score_updated = self.update_score_in_databases(
                    project_info['id'], 
                    project_info['name'], 
                    score,
                    denominator
                )
                if score_updated:
                    logger.info(f"[{thread_name}] Raw Score and Denominator successfully updated in databases")
                else:
                    logger.warning(f"[{thread_name}] Failed to update score fields in one or more databases")
            else:
                # Empty report but not a 500 error
                logger.error(f"[{thread_name}] Research failed - no output generated")
                self.update_research_status(project_info['id'], "error")
                logger.error(f"[{thread_name}] [{position}/{total}] ✗ Research failed with no output")
                result['error'] = 'No output generated'
                
        except Exception as e:
            error_str = str(e)
            
            # Check for 500 or 424 errors first
            if "Error code: 500" in error_str or "Error code: 424" in error_str:
                error_code = "500" if "Error code: 500" in error_str else "424"
                with self._lock:
                    self.error_500_count += 1
                    logger.error(f"[{thread_name}] Got {error_code} error (count: {self.error_500_count}/{self.max_500_errors})")
                    logger.error(f"[{thread_name}] [{position}/{total}] {error_code} Error #{self.error_500_count} - skipping silently")
                    
                    if self.error_500_count >= self.max_500_errors:
                        self.should_terminate = True
                        logger.error(f"TERMINATING: Too many 500/424 errors ({self.max_500_errors})")
                        
                        # Don't exit from worker thread - let it return naturally
                        logger.error("Signaling shutdown due to excessive 500/424 errors")
                
                # Revert status back to original
                original_status = project_info.get('research_status', [])
                if 'error' in original_status:
                    self.update_research_status(project_info['id'], "error")
                else:
                    try:
                        self.notion.pages.update(
                            page_id=project_info['id'],
                            properties={
                                "Research Status": {
                                    "multi_select": []
                                }
                            }
                        )
                    except:
                        pass
                
                result['error'] = f'{error_code} error - skipped'
                # Don't upload error report for 500s
                return result
            
            # For non-500 errors, proceed with error reporting
            logger.error(f"[{thread_name}] Exception during research: {type(e).__name__}: {str(e)}")
            logger.exception(f"[{thread_name}] Full stack trace:")
            logger.error(f"[{thread_name}] [{position}/{total}] Error processing project: {e}")
            result['error'] = str(e)
            
            # Log error details
            self._log_error_details(e, project_info, project_logger=None)
            
            # Try to upload error report
            try:
                # Clean up HTML error messages
                if "<!DOCTYPE html>" in error_str:
                    if "502" in error_str:
                        error_message = "502 Bad Gateway - OpenAI API infrastructure error"
                    elif "503" in error_str:
                        error_message = "503 Service Unavailable - OpenAI API is temporarily down"
                    else:
                        error_message = "HTML error page received - API communication error"
                else:
                    error_message = error_str[:500] + "..." if len(error_str) > 500 else error_str
                
                error_report = f"""# Research Error Report

## Error Details
- **Project**: {project_info['name']}
- **Error Type**: {type(e).__name__}
- **Error Message**: {error_message}
- **Thread**: {thread_name}
- **Timestamp**: {datetime.now().isoformat()}

## Recommended Actions
1. {"Wait 5-10 minutes and retry if this is a 502/503 error" if "502" in error_str or "503" in error_str else "Check the agent logs for detailed error information"}
2. Verify all API keys and server connectivity
3. Contact support if the error persists
"""
                # Get the project directory where StreamingProcessor writes files
                project_dir = self.get_project_directory(project_info)
                    
                url = self.update_notion_with_research(
                    project_info['id'],
                    project_info['name'],
                    error_report,
                    project_dir
                )
                result['url'] = url
                logger.warning(f"[{thread_name}] [{position}/{total}] ⚠ Exception occurred but error report uploaded: {url}")
            except:
                logger.error(f"[{thread_name}] [{position}/{total}] Failed to upload error report")
            
            self.update_research_status(project_info['id'], "error")
        
        # Log final summary
        logger.info(f"[{thread_name}] \n" + "="*80)
        logger.info(f"[{thread_name}] RESEARCH SUMMARY")
        logger.info(f"[{thread_name}] " + "="*80)
        logger.info(f"[{thread_name}] Project: {project_info['name']}")
        logger.info(f"[{thread_name}] Success: {result['success']}")
        logger.info(f"[{thread_name}] URL: {result.get('url', 'N/A')}")
        logger.info(f"[{thread_name}] Error: {result.get('error', 'None')}")
        logger.info(f"[{thread_name}] Thread: {thread_name}")
        logger.info(f"[{thread_name}] Log directory: {self.get_project_directory(project_info)}")
        logger.info(f"[{thread_name}] " + "="*80 + "\n")
        
        return result
    
    def process_batch_parallel(self, projects: List[Dict], max_workers: int = 5, override_research: bool = False) -> Dict[str, Any]:
        """Process multiple projects in parallel with robust error handling.
        
        Args:
            projects: List of projects to process
            max_workers: Maximum number of parallel workers
            override_research: If True, override early exit rules for later-stage projects
        """
        total = len(projects)
        results = {
            'successful': 0,
            'failed': 0,
            'errors': [],
            'urls': [],
            'duration': 0
        }
        
        start_time = time.time()
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting parallel processing of {total} projects with {max_workers} workers")
        logger.info(f"{'='*60}\n")
        
        # Create thread pool
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='Worker') as executor:
            # Submit all tasks
            future_to_project = {}
            submitted_count = 0
            for i, project in enumerate(projects):
                # Check if we should stop submitting new tasks
                if self.should_terminate:
                    logger.error(f"Stopping submission of new tasks due to too many 500 errors")
                    logger.error(f"Submitted {submitted_count} of {total} projects before termination")
                    break
                    
                project_info = self.extract_project_info(project)
                future = executor.submit(self.process_single_project, project_info, i+1, total, override_research)
                future_to_project[future] = project_info
                submitted_count += 1
                # Small delay to avoid overwhelming the MCP server at startup
                time.sleep(0.1)
            
            # Process completed tasks with early termination check
            completed_count = 0
            for future in as_completed(future_to_project):
                # Check if we should abort processing remaining futures
                if self.should_terminate and completed_count > 0:
                    logger.warning(f"Terminating early - cancelling {len(future_to_project) - completed_count - 1} remaining tasks")
                    # Cancel all pending futures
                    for f in future_to_project:
                        if not f.done():
                            f.cancel()
                    # Shutdown executor immediately
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                project_info = future_to_project[future]
                try:
                    result = future.result(timeout=1)  # Add timeout to avoid hanging
                    completed_count += 1
                    if result['success']:
                        results['successful'] += 1
                        results['urls'].append(result['url'])
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'project': project_info['name'],
                            'error': result['error'],
                            'thread': result['thread']
                        })
                except Exception as e:
                    completed_count += 1
                    results['failed'] += 1
                    results['errors'].append({
                        'project': project_info['name'],
                        'error': f"Thread execution failed: {str(e)}",
                        'thread': 'Unknown'
                    })
                    logger.error(f"Thread execution failed for {project_info['name']}: {e}")
        
        # Calculate duration
        results['duration'] = time.time() - start_time
        
        # Log summary
        logger.info(f"\n{'='*60}")
        logger.info(f"Parallel Processing {'TERMINATED EARLY' if self.should_terminate else 'Complete'}")
        logger.info(f"{'='*60}")
        logger.info(f"Total Projects: {total}")
        logger.info(f"Successful: {results['successful']}")
        logger.info(f"Failed: {results['failed']}")
        logger.info(f"Skipped: {total - results['successful'] - results['failed']}")
        logger.info(f"Duration: {results['duration']:.2f} seconds")
        if results['successful'] + results['failed'] > 0:
            logger.info(f"Average time per processed project: {results['duration']/(results['successful'] + results['failed']):.2f} seconds")
        
        if self.should_terminate:
            logger.error(f"TERMINATED EARLY: Too many 500/424 errors ({self.error_500_count}/{self.max_500_errors})")
            logger.error(f"Projects not processed: {total - results['successful'] - results['failed']}")
            
            # Exit from main thread after graceful cleanup
            logger.error("Exiting Ava due to excessive 500/424 errors")
            import sys
            sys.exit(1)
        
        if results['errors']:
            logger.info(f"\nErrors encountered:")
            for error in results['errors']:
                logger.info(f"  - {error['project']} ({error['thread']}): {error['error']}")
        
        return results


def main():
    parser = argparse.ArgumentParser(description='Research Agent for Notion Projects')
    parser.add_argument('--batch-size', type=int, default=10,
                       help='Number of projects to process (default: 10)')
    parser.add_argument('--project-id', type=str,
                       help='Research a specific project by ID')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without executing')
    parser.add_argument('--sequential', action='store_true',
                       help='Process projects sequentially instead of parallel (parallel is default)')
    parser.add_argument('--workers', type=int, default=10,
                       help='Number of parallel workers (default: 10, max: 10)')
    parser.add_argument('--instant', action='store_true',
                       help='Use instant processing for faster results (more expensive, 15min timeout)')
    parser.add_argument('--model', type=str, default=None,
                       help='Model to use for research (override OPENAI_MODEL env)')
    parser.add_argument('--override_research', action='store_true',
                       help='Override early exit rules for later-stage projects')
    parser.add_argument('--prompt', type=str,
                       help='Path to custom prompt .md file (default: research_agent_prompt_al.md)')
    parser.add_argument('--twitter', type=str,
                       help='Research a Twitter handle directly without Notion (e.g., @username or username)')
    
    args = parser.parse_args()
    
    # Load system prompt based on arguments
    global SYSTEM_MESSAGE
    if args.prompt:
        # Validate file exists and is readable
        if not os.path.exists(args.prompt):
            logger.error(f"Custom prompt file not found: {args.prompt}")
            return
        if not args.prompt.endswith('.md'):
            logger.warning(f"Custom prompt file should be a .md file, got: {args.prompt}")
        SYSTEM_MESSAGE = load_system_prompt(args.prompt)
        logger.info(f"Using custom prompt file: {args.prompt}")
    else:
        # Load default prompt
        SYSTEM_MESSAGE = load_system_prompt()
        logger.info("Using default prompt: research_agent_prompt_al.md")

    # Resolve model: CLI override wins, otherwise OPENAI_MODEL env, otherwise fail
    env_model = os.environ.get("OPENAI_MODEL")
    resolved_model = args.model or env_model
    if not resolved_model:
        logger.error("Missing model configuration. Set OPENAI_MODEL in the environment or provide --model.")
        return
    
    # Validate workers count
    if args.workers > 10:
        logger.warning("Maximum workers limited to 10 to avoid overwhelming APIs")
        args.workers = 10
    
    # Log startup info
    logger.info(f"Research Agent started")
    logger.info(f"Session directory: {session_dir}")
    logger.info(f"Console log: {main_log_file}")
    logger.info(f"Configuration: batch_size={args.batch_size}, dry_run={args.dry_run}, sequential={args.sequential}, workers={args.workers}, instant={args.instant}, model={resolved_model}, custom_prompt={bool(args.prompt)}")
    
    # Validate configuration
    if not all([OPENAI_API_KEY, NOTION_API_KEY, NOTION_DATABASE_ID]):
        logger.error("Missing required environment variables")
        logger.error("Please ensure the following are set:")
        logger.error("- OPENAI_API_KEY")
        logger.error("- NOTION_API_KEY") 
        logger.error("- NOTION_DATABASE_ID")
        return
    
    # Ensure MCP server is running
    try:
        import requests
        # Try the health endpoint first, fallback to base URL
        try:
            response = requests.get(MCP_SERVER_URL.replace('/sse', '/health'), timeout=5)
        except:
            response = requests.get(MCP_SERVER_URL.replace('/sse', ''), timeout=5)
        
        if response.status_code not in [200, 404]:  # 404 is ok if health endpoint doesn't exist
            logger.error(f"MCP server not responding at {MCP_SERVER_URL}")
            return
    except Exception as e:
        logger.error(f"Cannot connect to MCP server at {MCP_SERVER_URL}")
        logger.info("Please ensure the MCP server is running: python main.py")
        return
    
    # Initialize agent with flex flag (default True unless --instant is used), model, and system message
    agent = ResearchAgent(use_flex=not args.instant, model=resolved_model, system_message=SYSTEM_MESSAGE)
    
    # Log if override flag is set
    if args.override_research:
        logger.info("Override research flag is set - will research later-stage projects")
    
    # Handle direct Twitter research without Notion
    if args.twitter:
        # Clean the Twitter handle
        twitter_handle = args.twitter.strip().replace('@', '')
        logger.info(f"Direct Twitter research mode: @{twitter_handle}")
        
        # Minimal project info - just what's needed for research_project method
        project_info = {
            'id': f'twitter_{twitter_handle}',
            'name': f'@{twitter_handle}',
            'twitter_handles': [twitter_handle],
            'summary': '',
            'research_status': []
        }
        
        # Use existing research_project method - it handles everything
        report = agent.research_project(project_info, override_research=args.override_research, position=1, total=1)
        
        if report:
            # Extract scoring data
            score, denominator, priority = agent.extract_scoring_data(report)
            
            # Save report to file in session directory
            report_file = os.path.join(session_dir, f'{twitter_handle}_research.md')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"✓ Research complete for @{twitter_handle}")
            logger.info(f"  Score: {score}/{denominator}, Priority: {priority}")
            logger.info(f"  Report saved to: {report_file}")
        else:
            logger.error(f"✗ Research failed for @{twitter_handle}")
        
        return
    
    if args.project_id:
        # Research specific project
        logger.info(f"Researching specific project: {args.project_id}")
        project = agent.notion.pages.retrieve(page_id=args.project_id)
        project_info = agent.extract_project_info(project)
        
        if args.dry_run:
            logger.info(f"Would research: {project_info['name']}")
            logger.info(f"Twitter handles: {project_info['twitter_handles']}")
            return
        
        agent.update_research_status(args.project_id, "in progress")
        report = agent.research_project(project_info, override_research=args.override_research, position=1, total=1)
        
        if report is None:
            # 500 error - revert status, don't upload
            logger.error(f"500 error - project remains unresearched")
            # Revert to empty status for retry
            try:
                agent.notion.pages.update(
                    page_id=args.project_id,
                    properties={
                        "Research Status": {
                            "multi_select": []
                        }
                    }
                )
            except:
                pass
        elif report:
            # Check if it's an error report
            is_error = "# Research Error Report" in report
            
            # Get the project directory where StreamingProcessor writes files
            project_dir = agent.get_project_directory(project_info)
                
            url = agent.update_notion_with_research(
                args.project_id,
                project_info['name'],
                report,
                project_dir
            )
            
            if is_error:
                agent.update_research_status(args.project_id, "error")
                logger.warning(f"Research had errors but report uploaded: {url}")
            else:
                meta_monitor = agent.extract_monitor_flag(report)
                if meta_monitor is True:
                    agent.update_research_status(args.project_id, "monitor")
                    logger.info(f"Research complete (monitor): {url}")
                else:
                    agent.update_research_status(args.project_id, "completed")
                    logger.info(f"Research complete: {url}")
            
            # Extract and update score
            score, denominator, priority = agent.extract_scoring_data(report)
            if score >= 0 and denominator > 0:
                logger.info(f"Valid scoring: {score}/{denominator}, Priority: {priority}")
            else:
                logger.warning(f"Invalid or missing scoring data (score={score}, denominator={denominator}), will store -1")
                score = -1
                # Keep denominator as detected/defaulted by extract_scoring_data
            
            # Always update the scores
            agent.update_score_in_databases(args.project_id, project_info['name'], score, denominator)
        else:
            # Empty report but not 500
            agent.update_research_status(args.project_id, "error")
            logger.error("Research failed with no output")
    else:
        # Process batch
        projects = agent.get_unresearched_projects(args.batch_size)
        logger.info(f"Found {len(projects)} unresearched projects")
        
        if args.dry_run:
            for project in projects:
                info = agent.extract_project_info(project)
                logger.info(f"Would research: {info['name']}")
            return
        
        # Check if sequential processing is explicitly requested
        if args.sequential:
            # Sequential processing (legacy behavior)
            logger.info("Using sequential processing (--sequential flag specified)")
        elif len(projects) == 1:
            # Single project, no need for parallel
            logger.info("Processing single project")
        else:
            # Parallel processing is default for multiple projects
            logger.info(f"Using parallel processing with {args.workers} workers (default mode)")
            results = agent.process_batch_parallel(projects, max_workers=args.workers, override_research=args.override_research)
            logger.info(f"\nBatch processing complete: {results['successful']} successful, {results['failed']} failed")
            return
        
        # Sequential processing code continues below
        for i, project in enumerate(projects):
            # Check if we should terminate early
            if agent.should_terminate:
                logger.error(f"TERMINATING: Too many 500/424 errors ({agent.error_500_count}/{agent.max_500_errors})")
                logger.error(f"Skipping remaining {len(projects) - i} projects")
                break
                
            project_info = agent.extract_project_info(project)
            is_error_retry = 'error' in project_info.get('research_status', [])
            is_stuck_retry = 'in progress' in project_info.get('research_status', [])
            retry_msg = ""
            if is_error_retry:
                retry_msg = " (RETRY - previous error)"
            elif is_stuck_retry:
                retry_msg = " (RETRY - stuck in progress)"
            logger.info(f"\n[{i+1}/{len(projects)}] Researching: {project_info['name']}{retry_msg}")
            
            try:
                agent.update_research_status(project_info['id'], "in progress")
                report = agent.research_project(project_info, override_research=args.override_research, position=i+1, total=len(projects))
                
                if report is None:
                    # 500/424 error - revert status, don't upload
                    logger.error(f"⚠ 500/424 error - skipping, project remains unresearched")
                    # Revert status back to what it was
                    original_status = project_info.get('research_status', [])
                    if 'error' in original_status:
                        agent.update_research_status(project_info['id'], "error")
                    else:
                        try:
                            agent.notion.pages.update(
                                page_id=project_info['id'],
                                properties={
                                    "Research Status": {
                                        "multi_select": []
                                    }
                                }
                            )
                        except:
                            pass
                elif report:
                    # Check if it's an error report
                    is_error = "# Research Error Report" in report or "# Partial Research Results" in report
                    
                    # Get the project directory where StreamingProcessor writes files
                    project_dir = agent.get_project_directory(project_info)
                        
                    url = agent.update_notion_with_research(
                        project_info['id'],
                        project_info['name'],
                        report,
                        project_dir
                    )
                    
                    if is_error:
                        agent.update_research_status(project_info['id'], "error")
                        logger.warning(f"⚠ Errors occurred but report uploaded: {url}")
                    else:
                        meta_monitor = agent.extract_monitor_flag(report)
                        if meta_monitor is True:
                            agent.update_research_status(project_info['id'], "monitor")
                            logger.info(f"✓ Complete (monitor): {url}")
                        else:
                            agent.update_research_status(project_info['id'], "completed")
                            logger.info(f"✓ Complete: {url}")
                    
                    # Extract and update score
                    score, denominator, priority = agent.extract_scoring_data(report)
                    if score >= 0 and denominator > 0:
                        logger.info(f"Valid scoring: {score}/{denominator}, Priority: {priority}")
                    else:
                        logger.warning(f"Invalid or missing scoring data (score={score}, denominator={denominator}), will store -1")
                        score = -1
                        # Keep denominator as detected/defaulted by extract_scoring_data
                    
                    # Always update the scores
                    agent.update_score_in_databases(project_info['id'], project_info['name'], score, denominator)
                else:
                    # Empty report but not 500
                    agent.update_research_status(project_info['id'], "error")
                    logger.error("✗ Failed with no output")
            except Exception as e:
                error_str = str(e)
                
                # Check for 500 or 424 errors first
                if "Error code: 500" in error_str or "Error code: 424" in error_str:
                    error_code = "500" if "Error code: 500" in error_str else "424"
                    agent.error_500_count += 1
                    logger.error(f"{error_code} Error #{agent.error_500_count} encountered for {project_info['name']} - skipping silently")
                    
                    if agent.error_500_count >= agent.max_500_errors:
                        agent.should_terminate = True
                        logger.error(f"TERMINATING: Too many 500/424 errors ({agent.max_500_errors})")
                        
                        # Exit gracefully from main thread
                        logger.error("Exiting Ava due to excessive 500/424 errors")
                        import sys
                        sys.exit(1)
                    
                    # Revert status back to original
                    original_status = project_info.get('research_status', [])
                    if 'error' in original_status:
                        agent.update_research_status(project_info['id'], "error")
                    else:
                        try:
                            agent.notion.pages.update(
                                page_id=project_info['id'],
                                properties={
                                    "Research Status": {
                                        "multi_select": []
                                    }
                                }
                            )
                        except:
                            pass
                    continue  # Skip to next project
                
                # For non-500 errors, upload error report
                logger.error(f"Error processing project: {e}")
                # Try to upload an error report even for exceptions
                try:
                    # Clean up HTML error messages
                    if "<!DOCTYPE html>" in error_str:
                        if "502" in error_str:
                            error_message = "502 Bad Gateway - OpenAI API infrastructure error"
                        elif "503" in error_str:
                            error_message = "503 Service Unavailable - OpenAI API is temporarily down"
                        else:
                            error_message = "HTML error page received - API communication error"
                    else:
                        error_message = error_str[:500] + "..." if len(error_str) > 500 else error_str
                    
                    error_report = f"""# Research Error Report

## Error Details
- **Project**: {project_info['name']}
- **Error Type**: {type(e).__name__}
- **Error Message**: {error_message}
- **Timestamp**: {datetime.now().isoformat()}

## Recommended Actions
1. {"Wait 5-10 minutes and retry if this is a 502/503 error" if "502" in error_str or "503" in error_str else "Check the agent logs for detailed error information"}
2. Verify all API keys and server connectivity
3. Contact support if the error persists
"""
                    # Get the project directory where StreamingProcessor writes files
                    project_dir = agent.get_project_directory(project_info)
                        
                    url = agent.update_notion_with_research(
                        project_info['id'],
                        project_info['name'],
                        error_report,
                        project_dir
                    )
                    logger.warning(f"⚠ Exception occurred but error report uploaded: {url}")
                except:
                    logger.error("Failed to upload error report")
                agent.update_research_status(project_info['id'], "error")

if __name__ == "__main__":
    main()
