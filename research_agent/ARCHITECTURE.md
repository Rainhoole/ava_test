# Research Agent Architecture (High-Level)

This document describes the runtime architecture of the Research Agent implemented in `research_agent/research_agent.py` and the modules it coordinates.

## What It Does

The Research Agent:
- pulls a worklist of projects from a Notion database (or accepts a direct Twitter handle),
- runs an OpenAI streaming “research” call that can use tools (web search + MCP tool servers),
- writes local per-project logs/artifacts,
- updates the existing Notion page with the generated report and structured metadata (status, priority, stage, scores).

## Primary Components

- **CLI + Orchestrator** (`research_agent/research_agent.py`)
  - Parses CLI args, loads system prompt, validates configuration, and chooses run mode.
  - Queries Notion for “unresearched” projects and filters them (including “stuck” in-progress items).
  - Executes projects sequentially or in parallel using a `ThreadPoolExecutor`.
  - Applies status changes and writes score fields back to Notion.

- **Research Execution (Streaming)** (`research_agent/streaming_processor.py`)
  - Wraps the OpenAI Responses API streaming call.
  - Configures tools available to the model:
    - `web_search` (OpenAI-hosted)
    - MCP server labeled `research_tools` (configurable via `MCP_SERVER_URL`)
    - MCP server labeled `firecrawl` (remote)
  - Implements retry logic for 424 (MCP dependency), 429 (rate limiting), and 502/503 (infrastructure).

- **Streaming Event Logging** (`research_agent/streaming_logger.py`)
  - Consumes streaming chunks and writes artifacts per project:
    - `01_summary.log`, `02_reasoning.md`, `03_tools.jsonl`, `04_metrics.json`, `final_output.md`, `raw_events.jsonl`

- **Notion Persistence Layer** (`research_agent/notion_updater.py`)
  - Updates page properties (status/date/priority/stage, plus category score properties).
  - Converts markdown report output into Notion blocks and appends them (batched).
  - Optionally creates a child page for the reasoning file if `02_reasoning.md` exists in the project log folder.
  - Optionally syncs data into a second Notion database (`NOTION_DATABASE_ID_EXT`).

- **External Services**
  - **Notion API**: worklist source and destination for updates.
  - **OpenAI Responses API**: generates the research report and executes tool calls.
  - **MCP Server** (`MCP_SERVER_URL`): provides domain-specific tools the model can call.
  - **Firecrawl MCP** (remote): web extraction tool server available to the model.
  - **S3 (optional)** (`research_agent/s3_logs.py`): uploads per-project logs if AWS credentials are configured.

## Data & Artifacts

- **Session directory**: `logs/projects_YYYYMMDD/`
- **Per-project directory** (handle-based): `logs/projects_YYYYMMDD/<twitter_handle>/`
- **Notion outputs**:
  - Page properties updated (Research Status/Date/Priority/Stage + score properties)
  - Research content appended as blocks into the existing page

## Architecture Diagram

```mermaid
flowchart LR
  subgraph CLI["CLI + Orchestrator"]
    A["research_agent/research_agent.py\n(argparse + ResearchAgent)"]
  end

  subgraph Notion["Notion"]
    N1[(Main Database<br/>NOTION_DATABASE_ID)]
    N2[(External Database (optional)<br/>NOTION_DATABASE_ID_EXT)]
  end

  subgraph OpenAI["OpenAI"]
    OA[(Responses API<br/>(streaming))]
    WS["Tool: web_search"]
  end

  subgraph MCP["Tool Servers (MCP)"]
    MCP1[(research_tools<br/>MCP_SERVER_URL)]
    MCP2[(firecrawl<br/>remote MCP server)]
  end

  subgraph Logs["Logging/Artifacts"]
    FS[(Local filesystem<br/>logs/projects_YYYYMMDD/&lt;handle&gt;/)]
    S3[(S3 (optional)<br/>S3_BUCKET)]
  end

  A -->|query worklist| N1
  A -->|status + report + scores| N1
  A -.->|optional score sync| N2

  A --> SP["StreamingProcessor"]
  SP -->|responses.create(stream)| OA
  OA --> WS
  OA -->|tool calls| MCP1
  OA -->|tool calls| MCP2

  SP --> SL["StreamingLogger"]
  SL --> FS
  FS -.->|optional upload| S3

  A --> NU["NotionUpdater"]
  NU -->|properties + blocks| N1
  NU -.->|optional sync| N2
```
