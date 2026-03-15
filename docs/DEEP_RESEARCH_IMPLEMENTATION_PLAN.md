# Deep Research System - Implementation Plan

## Executive Summary

This implementation plan describes a two-component architecture for AI-powered research on blockchain/crypto projects:

1. **MCP Server** (main.py) - Already implemented, provides Twitter and web tools via FastMCP/SSE
2. **Research Agent** (NEW) - Command-line tool that orchestrates OpenAI GPT O3 with MCP tools for autonomous research

The Research Agent pulls projects from Notion, executes one-shot research requests using the same approach as api_test.py, and uploads comprehensive reports back to Notion. This separation ensures the MCP server remains a pure tool provider while the agent handles all orchestration logic.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Implementation Phases](#implementation-phases)
3. [Module Specifications](#module-specifications)
4. [Command-Line Interface](#command-line-interface)
5. [Database Integration](#database-integration)
6. [Testing Strategy](#testing-strategy)
7. [Future Enhancement Points](#future-enhancement-points)

## System Architecture

### Overview

The system consists of two independent components:

1. **MCP Server (Existing)**: Runs on port 8000, provides 6 tools via FastMCP/SSE
2. **Research Agent (New)**: Command-line tool that uses OpenAI O3 + MCP tools

### Component Architecture

```
┌─────────────────────────────────────────────────┐
│                  EXISTING                       │
├─────────────────────────────────────────────────┤
│  MCP Server (main.py)                           │
│  - Runs on http://localhost:8000/sse            │
│  - Provides 6 tools via FastMCP                 │
│  - Twitter: profile, following, tweets, bulk    │
│  - Web: scrape_website, search_web             │
└─────────────────────────────────────────────────┘
                         ⬆️
                    SSE Protocol
                         ⬇️
┌─────────────────────────────────────────────────┐
│                    NEW                          │
├─────────────────────────────────────────────────┤
│  Research Agent (research_agent.py)             │
│  - Command-line interface                       │
│  - Notion client for project retrieval          │
│  - OpenAI O3 integration (like api_test.py)     │
│  - Single-shot research execution               │
│  - Notion page creation with results            │
├─────────────────────────────────────────────────┤
│  Workflow:                                      │
│  1. Query Notion for "not researched" projects  │
│  2. For each project:                           │
│     a. Update status to "in progress"           │
│     b. Execute O3 research (one API call)       │
│     c. Create Notion page with report           │
│     d. Update status to "completed"             │
└─────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Separation of Concerns**: MCP server (main.py) remains unchanged; research logic in separate agent
2. **Agentic Approach**: Each research task is one OpenAI O3 API call with all tools available
3. **Reuse api_test.py Pattern**: Copy the working O3 integration approach from api_test.py
4. **Notion as State Manager**: Database tracks research status; agent polls and updates
5. **No Code Changes to MCP**: Leave main.py and tools.py untouched; agent uses existing endpoints

## Implementation Phases

### Phase 1: Research Agent Setup (Day 1-2)

1. **File Organization**
   - Create `research_agent.py` in root directory (not a subdirectory)
   - Copy OpenAI O3 integration code from `api_test.py`
   - Add Notion client dependencies to requirements.txt

2. **Notion Integration**
   - Copy Notion config from `reference_project/twitter-vc-analyzer-master/.env`
   - Add "Research Status" field to existing database
   - Implement query/update functions for project status

3. **Core Agent Structure**
   ```python
   # research_agent.py structure:
   # 1. Load environment variables
   # 2. Initialize Notion client
   # 3. Query projects with "not researched" status
   # 4. For each project:
   #    - Extract project info (name, twitter handles)
   #    - Build research prompt
   #    - Execute O3 API call with MCP tools
   #    - Parse research results
   #    - Create Notion page with report
   #    - Update project status
   ```

### Phase 2: OpenAI O3 Integration (Day 2-3)

1. **Copy Working Code from api_test.py**
   ```python
   # Key components to copy:
   - OpenAI client initialization
   - System message (research prompt)
   - O3 API call structure with MCP tools
   - Response parsing logic
   ```

2. **Adapt System Message**
   - Use existing comprehensive prompt from api_test.py
   - Modify user_query to include project-specific info:
     ```python
     user_query = f"Research {project_name} - Twitter: {twitter_handles}"
     ```

3. **MCP Tool Configuration**
   - Keep exact same tool setup as api_test.py:
     ```python
     tools=[{
         "type": "mcp",
         "server_label": "research_tools",
         "server_url": "http://localhost:8000/sse",
         "require_approval": "never"
     }]
     ```

### Phase 3: Notion Report Creation (Day 3-4)

1. **Extract Final Answer**
   ```python
   # From O3 response, find step with type="final_answer"
   final_answer = None
   for step in response.output:
       if step.type == "final_answer":
           final_answer = step.content[0].text
           break
   ```

2. **Create Notion Page**
   - Page title: "{Project Name} - Research Report"
   - Convert markdown sections to Notion blocks
   - Include all citations from O3 response
   - Add timestamp and research metadata

### Phase 4: Testing & Error Handling (Day 4-5)

1. **Error Handling**
   - Graceful handling of O3 API failures
   - Retry logic for transient errors
   - Proper status updates on failures

2. **Testing Approach**
   - Test with 1-2 projects first
   - Verify Notion page creation
   - Check research quality matches api_test.py output

## Code Reorganization Requirements

### Current State
- `main.py`: MCP server implementation (NO CHANGES)
- `tools.py`: Tool implementations (NO CHANGES)
- `api_test.py`: Working O3 integration example (REFERENCE ONLY)

### New Files Needed

#### 1. research_agent.py (Main Entry Point)

```python
import os
import json
import logging
import argparse
from typing import Dict, List, Optional
from datetime import datetime

# Clear proxy vars (copied from api_test.py)
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from openai import OpenAI
from notion_client import Client
from dotenv import load_dotenv

# Load environment
load_dotenv('reference_project/twitter-vc-analyzer-master/.env')
load_dotenv()  # Also load main .env

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")

# System message from api_test.py (unchanged)
SYSTEM_MESSAGE = """[COPY EXACT SYSTEM MESSAGE FROM api_test.py LINES 56-143]"""

class ResearchAgent:
    def __init__(self):
        self.openai = OpenAI(api_key=OPENAI_API_KEY)
        self.notion = Client(auth=NOTION_API_KEY)
        self.database_id = NOTION_DATABASE_ID
        
    def get_unresearched_projects(self, limit: int = 5) -> List[Dict]:
        """Query Notion for projects marked as 'not researched'"""
        response = self.notion.databases.query(
            database_id=self.database_id,
            filter={
                "property": "Research Status",
                "multi_select": {"contains": "not researched"}
            },
            page_size=limit
        )
        return response.get('results', [])
    
    def extract_project_info(self, project: Dict) -> Dict:
        """Extract key information from Notion project"""
        props = project.get('properties', {})
        
        # Extract text properties
        name = self._get_text_property(props.get('Name', {}))
        twitter = self._get_text_property(props.get('Twitter', {}))
        summary = self._get_text_property(props.get('Summary', {}))
        
        return {
            'id': project['id'],
            'name': name,
            'twitter_handles': [twitter] if twitter else [],
            'summary': summary
        }
    
    def research_project(self, project_info: Dict) -> Optional[str]:
        """Execute O3 research on a single project"""
        # Build user query
        user_query = f"Research {project_info['name']}"
        if project_info['twitter_handles']:
            user_query += f" - Twitter: {', '.join(project_info['twitter_handles'])}"
        
        logger.info(f"Researching: {user_query}")
        
        try:
            # Execute O3 API call (copied from api_test.py)
            response = self.openai.responses.create(
                model="o3",
                input=[
                    {"role": "developer", "content": [{"type": "input_text", "text": SYSTEM_MESSAGE}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user_query}]}
                ],
                tools=[
                    {"type": "web_search_preview"},
                    {
                        "type": "mcp",
                        "server_label": "research_tools",
                        "server_url": MCP_SERVER_URL,
                        "require_approval": "never"
                    }
                ],
                reasoning={"effort": "high"},
            )
            
            # Extract final answer
            for step in response.output:
                if step.type == "final_answer":
                    return step.content[0].text
                    
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return None
    
    def create_notion_report(self, project_id: str, report: str) -> str:
        """Create a new page in Notion with the research report"""
        # Implementation continues...
```

#### 2. Notion Integration Details

```python
# Notion helper methods (part of ResearchAgent class)

def update_research_status(self, page_id: str, status: str):
    """Update the Research Status property of a project"""
    self.notion.pages.update(
        page_id=page_id,
        properties={
            "Research Status": {
                "multi_select": [{"name": status}]
            }
        }
    )

def create_notion_report(self, project_id: str, project_name: str, report_content: str) -> str:
    """Create a new research report page in Notion"""
    # Parse markdown report into sections
    sections = self._parse_markdown_sections(report_content)
    
    # Create Notion blocks
    blocks = []
    for section in sections:
        if section['type'] == 'heading1':
            blocks.append({
                "type": "heading_1",
                "heading_1": {"rich_text": [{"text": {"content": section['content']}}]}
            })
        elif section['type'] == 'heading2':
            blocks.append({
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": section['content']}}]}
            })
        elif section['type'] == 'bullet':
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": section['content']}}]}
            })
        else:
            blocks.append({
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": section['content']}}]}
            })
    
    # Create the page
    response = self.notion.pages.create(
        parent={"database_id": self.database_id},
        properties={
            "Name": {"title": [{"text": {"content": f"{project_name} - Research Report"}}]},
            "Date": {"date": {"start": datetime.now().isoformat()}},
            "Category": {"multi_select": [{"name": "Research Report"}]}
        },
        children=blocks
    )
    
    return response['url']

def _get_text_property(self, prop: Dict) -> str:
    """Extract text from Notion property"""
    if prop.get('title'):
        return ''.join([t.get('plain_text', '') for t in prop['title']])
    elif prop.get('rich_text'):
        return ''.join([t.get('plain_text', '') for t in prop['rich_text']])
    return ""
```

#### 3. Main Execution Flow

```python
# Main execution (part of research_agent.py)

def main():
    parser = argparse.ArgumentParser(description='Research Agent for Notion Projects')
    parser.add_argument('--batch-size', type=int, default=5,
                       help='Number of projects to process')
    parser.add_argument('--project-id', type=str,
                       help='Research a specific project by ID')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without executing')
    
    args = parser.parse_args()
    
    # Validate configuration
    if not all([OPENAI_API_KEY, NOTION_API_KEY, NOTION_DATABASE_ID]):
        logger.error("Missing required environment variables")
        return
    
    # Ensure MCP server is running
    try:
        import requests
        response = requests.get(MCP_SERVER_URL.replace('/sse', '/health'))
        if response.status_code != 200:
            logger.error(f"MCP server not responding at {MCP_SERVER_URL}")
            return
    except:
        logger.error(f"Cannot connect to MCP server at {MCP_SERVER_URL}")
        logger.info("Please ensure the MCP server is running: python main.py")
        return
    
    # Initialize agent
    agent = ResearchAgent()
    
    if args.project_id:
        # Research specific project
        project = agent.notion.pages.retrieve(page_id=args.project_id)
        project_info = agent.extract_project_info(project)
        
        if not args.dry_run:
            agent.update_research_status(args.project_id, "in progress")
            report = agent.research_project(project_info)
            
            if report:
                url = agent.create_notion_report(
                    args.project_id,
                    project_info['name'],
                    report
                )
                agent.update_research_status(args.project_id, "completed")
                logger.info(f"Research complete: {url}")
            else:
                agent.update_research_status(args.project_id, "error")
                logger.error("Research failed")
    else:
        # Process batch
        projects = agent.get_unresearched_projects(args.batch_size)
        logger.info(f"Found {len(projects)} unresearched projects")
        
        if args.dry_run:
            for project in projects:
                info = agent.extract_project_info(project)
                logger.info(f"Would research: {info['name']}")
            return
        
        # Process each project
        for project in projects:
            project_info = agent.extract_project_info(project)
            logger.info(f"\nResearching: {project_info['name']}")
            
            agent.update_research_status(project_info['id'], "in progress")
            report = agent.research_project(project_info)
            
            if report:
                url = agent.create_notion_report(
                    project_info['id'],
                    project_info['name'],
                    report
                )
                agent.update_research_status(project_info['id'], "completed")
                logger.info(f"✓ Complete: {url}")
            else:
                agent.update_research_status(project_info['id'], "error")
                logger.error("✗ Failed")

if __name__ == "__main__":
    main()
```

## Implementation Steps for AI

### Step 1: Create research_agent.py

1. **Copy Core Structure from api_test.py**
   - Lines 1-54: Import statements and OpenAI client setup
   - Lines 56-143: SYSTEM_MESSAGE (keep exactly as is)
   - Lines 150-166: O3 API call structure
   - Lines 284-298: Final answer extraction logic

2. **Add Notion Integration**
   - Import notion-client
   - Load Notion credentials from .env
   - Implement project query and status update functions

3. **Adapt for Batch Processing**
   - Replace single user_query with project-specific queries
   - Add loop to process multiple projects
   - Implement proper error handling and status updates

### Step 2: Notion Database Setup

1. **Add Research Status Field**
   - Open Notion database (ID from .env)
   - Add multi-select property "Research Status"
   - Options: "not researched", "in progress", "completed", "error"

2. **Set Default Values**
   - Mark all existing projects as "not researched"
   - This enables the agent to find them

### Step 3: Environment Configuration

1. **Copy Notion Config**
   ```bash
   cp reference_project/twitter-vc-analyzer-master/.env .
   ```

2. **Verify All Keys Present**
   - OPENAI_API_KEY (for O3)
   - NOTION_API_KEY
   - NOTION_DATABASE_ID
   - MCP_SERVER_URL (default: http://localhost:8000/sse)

### Step 4: Testing Workflow

1. **Start MCP Server**
   ```bash
   python main.py  # Must be running for agent to work
   ```

2. **Test with Dry Run**
   ```bash
   python research_agent.py --dry-run --batch-size 1
   ```

3. **Run Single Project**
   ```bash
   python research_agent.py --project-id [NOTION_PAGE_ID]
   ```

4. **Process Batch**
   ```bash
   python research_agent.py --batch-size 5
   ```

## Key Implementation Notes

### 1. NO Changes to Existing Files
- `main.py` - MCP server remains untouched
- `tools.py` - Tool implementations remain untouched
- `api_test.py` - Reference only, do not modify

### 2. Single New File: research_agent.py
- All logic in one file (no subdirectories)
- Direct copy of O3 integration from api_test.py
- Minimal modifications for batch processing

### 3. Key Differences from api_test.py
- Add Notion client initialization
- Replace hardcoded user_query with project data
- Add batch processing loop
- Parse final_answer to create Notion pages
- Update project status throughout workflow

### 4. O3 API Call Pattern (MUST KEEP)
```python
# This exact structure from api_test.py MUST be preserved:
response = client.responses.create(
    model="o3",
    input=[...],  # System + user messages
    tools=[       # Web search + MCP tools
        {"type": "web_search_preview"},
        {
            "type": "mcp",
            "server_label": "research_tools",
            "server_url": mcp_server_url,
            "require_approval": "never"
        }
    ],
    reasoning={"effort": "high"}
)
```

### 5. Research Quality
- Each project gets ONE comprehensive O3 call
- O3 handles all tool orchestration internally
- System message drives research depth
- No need for custom research loops

## Migration Path for Existing Code

If you have existing research code:

1. **STOP using it** - Start fresh with research_agent.py
2. **Copy only Notion helpers** - If you have working Notion code
3. **Use api_test.py as template** - It's the proven pattern
4. **Don't overcomplicate** - One file, simple flow

## Usage Examples

```bash
# Start MCP server (required)
python main.py

# In another terminal:

# Process 5 unresearched projects (default)
python research_agent.py

# Process 10 projects
python research_agent.py --batch-size 10

# Research specific project
python research_agent.py --project-id "189101d80eba80dbab88cb55d29b670d"

# Dry run
python research_agent.py --dry-run
```

## Configuration

```bash
# Required environment variables:
OPENAI_API_KEY=sk-xxx        # For O3 API
NOTION_API_KEY=ntn_xxx       # From twitter-vc-analyzer
NOTION_DATABASE_ID=xxx       # From twitter-vc-analyzer
MCP_SERVER_URL=http://localhost:8000/sse  # MCP endpoint

# MCP server needs these (already in .env):
RAPID_API_KEY=xxx            # Twitter API
FIRECRAWL_API_KEY=xxx        # Web scraping
```

## Notion Database Configuration

### Required Schema Changes

Add ONE new field to existing database:

| Property | Type | Options | Purpose |
|----------|------|---------|-------|
| Research Status | Multi-select | not researched, in progress, completed, error | Track research workflow |

### Research Report Storage

**Option 1: Update Existing Project Page**
- Append research to "Details" field
- Preserves single source of truth
- Harder to format rich content

**Option 2: Create New Report Pages (RECOMMENDED)**
- Create child pages under project
- Full markdown formatting support
- Clear separation of original vs research
- Example: "{Project Name} - Research Report"

### Workflow States

1. **not researched** → Default for all existing projects
2. **in progress** → Set when O3 research starts
3. **completed** → Set after Notion report created
4. **error** → Set if research or upload fails

## Critical Success Factors

### 1. Keep It Simple
- One Python file: research_agent.py
- Direct copy of api_test.py patterns
- No complex abstractions or modules

### 2. Preserve O3 Integration
- EXACT same API call structure as api_test.py
- EXACT same system message
- EXACT same tool configuration
- Only change: user_query includes project info

### 3. MCP Server Independence
- Server runs separately (python main.py)
- Agent connects via SSE endpoint
- No modifications to server code

### 4. Notion Integration
- Minimal: query projects, update status, create pages
- Use notion-client library directly
- Simple markdown-to-blocks conversion

## Example Code Structure

```
openai_mcp/
├── main.py              # MCP server (NO CHANGES)
├── tools.py             # Tool implementations (NO CHANGES)
├── api_test.py          # Reference implementation (NO CHANGES)
├── research_agent.py    # NEW - All research logic here
├── requirements.txt     # Add: notion-client
└── .env                 # Add: NOTION_API_KEY, NOTION_DATABASE_ID
```

## Quick Start Commands

```bash
# 1. Install dependencies
pip install notion-client

# 2. Copy Notion config
cp reference_project/twitter-vc-analyzer-master/.env .

# 3. Add to .env:
# OPENAI_API_KEY=sk-xxx
# MCP_SERVER_URL=http://localhost:8000/sse

# 4. Start MCP server
python main.py

# 5. Test agent
python research_agent.py --dry-run

# 6. Run research
python research_agent.py --batch-size 1
```

## Summary for AI Implementation

### Architecture Change Summary

**OLD (Complex)**:
- Multiple modules and classes
- Custom research orchestration
- Complex iterative loops
- Many files and abstractions

**NEW (Simple)**:
- Two independent components: MCP server + Research agent
- Single research_agent.py file
- Direct copy of api_test.py approach
- One O3 API call per project
- Notion for state management

### Implementation Priority

1. **Create research_agent.py** - Copy api_test.py structure
2. **Add Notion integration** - Query projects, update status
3. **Test with one project** - Ensure quality matches api_test.py
4. **Add batch processing** - Loop through multiple projects
5. **NO changes to MCP server** - Keep main.py and tools.py as is

### Key Insight

The research agent is essentially api_test.py in a loop:
- Same O3 integration
- Same comprehensive prompt
- Same tool configuration
- Just different user_query per project

This approach leverages the proven pattern from api_test.py while adding minimal complexity for Notion integration and batch processing.

