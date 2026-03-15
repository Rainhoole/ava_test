# Research Agent Web Server

FastAPI server providing REST API for VC research agent operations using Claude Agent SDK with MCP servers, with a modern Next.js frontend.

## Quick Start

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Start server (default: v3 agent on port 8000)
python web_server.py

# Start with specific version
python web_server.py --version v1
python web_server.py --version v3

# Specify port
python web_server.py --port 8080
```

### Frontend

```bash
cd research-frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the app.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                               │
│                        research-frontend/                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Sidebar    │  │ MainPanel   │  │ LogViewer   │  │ReportViewer │    │
│  │ (Task List) │  │             │  │ (SSE Stream)│  │ (Markdown)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│                         Backend (FastAPI)                                │
│                          web_server.py                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  REST API Endpoints         │   Agent Runner                             │
│  ├─ POST /research          │   ├─ AgentRunnerV1 (Full system prompt)   │
│  ├─ GET  /tasks             │   └─ AgentRunnerV3 (Skill-based mode)     │
│  ├─ GET  /tasks/{id}        │                                           │
│  ├─ GET  /tasks/{id}/report │                                           │
│  ├─ GET  /tasks/{id}/stream │                                           │
│  └─ GET  /config            │                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                         MCP Servers                                      │
│  ┌─────────────────┐              ┌─────────────────┐                   │
│  │ twitter_mcp.py  │              │ firecrawl_mcp.py│                   │
│  │ ├─ get_profile  │              │ └─ scrape_url   │                   │
│  │ ├─ get_tweets   │              └─────────────────┘                   │
│  │ └─ get_following│                                                    │
│  └─────────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Frontend

The frontend is a modern Next.js application with a ChatGPT-style interface.

### Features

- **ChatGPT-style layout** with sidebar task list and main panel
- **Real-time log streaming** via Server-Sent Events (SSE)
- **Report viewing** with markdown rendering
- **Task management** - create, view, and cancel research tasks
- **Responsive design** with Tailwind CSS

### Tech Stack

- **Next.js 14** - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Lucide React** - Icons

### Environment Variables

Create `research-frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For deployment details, see [FRONTEND_DEPLOYMENT.md](./FRONTEND_DEPLOYMENT.md).

## Agent Versions

| Version | Description | Use Case |
|---------|-------------|----------|
| **v1** | Full system prompt mode | Maximum control, detailed prompt |
| **v3** | Skill-based mode | Uses `.claude/skills/vc-research` |

## API Endpoints

### Research

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/research` | Start new research task |
| GET | `/tasks` | List all tasks |
| GET | `/tasks/{task_id}` | Get task status |
| GET | `/tasks/{task_id}/report` | Get research report |
| GET | `/tasks/{task_id}/stream` | SSE stream for real-time progress |
| DELETE | `/tasks/{task_id}` | Cancel/delete task |

### Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/config` | Get server configuration |
| GET | `/health` | Health check |

### Web Fetch (Utility)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webfetch` | Scrape a URL via Firecrawl |

## Usage Examples

### Start a Research Task

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"handle": "@username"}'
```

Response:
```json
{
  "task_id": "abc123",
  "handle": "username",
  "status": "pending",
  "version": "v3"
}
```

### Check Task Status

```bash
curl http://localhost:8000/tasks/abc123
```

### Get Report

```bash
curl http://localhost:8000/tasks/abc123/report
```

### Stream Progress (SSE)

```bash
curl http://localhost:8000/tasks/abc123/stream \
  -H "Accept: text/event-stream"
```

## Environment Variables

Create `.env` file:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-xxx

# For Twitter tools (MCP server)
RAPID_API_KEY=xxx

# For web scraping (Firecrawl)
FIRECRAWL_API_KEY=xxx

# Optional
PORT=8000
```

## File Structure

```
research_agent_cowork/
├── web_server.py        # FastAPI server (main entry point)
├── agent_runner.py      # Agent runner implementations (v1, v3)
├── task_manager.py      # Task queue and state management
├── structured_logger.py # Logging utilities
├── twitter_mcp.py       # MCP server for Twitter API
├── firecrawl_mcp.py     # MCP server for web scraping
├── file_storage.py      # File storage utilities
├── requirements.txt     # Python dependencies
├── .claude/
│   └── skills/
│       └── vc-research/ # V3 skill definition
├── outputs/             # Generated reports
│   └── YYYYMMDD/
│       ├── handle_research.md   # Final report
│       ├── handle_messages.log  # Execution log
│       └── handle_messages.jsonl # Structured log for frontend
└── research-frontend/   # Next.js frontend application
    ├── src/
    │   ├── app/         # Next.js app router
    │   ├── components/  # React components
    │   ├── lib/         # API client & utilities
    │   └── types/       # TypeScript types
    ├── package.json
    └── vercel.json      # Vercel deployment config
```

## Command Line Options

```bash
python web_server.py [OPTIONS]

Options:
  --version, -v   Agent version: v1 or v3 (default: v3)
  --model, -m     Model to use (default: claude-opus-4-5-20251101)
  --port, -p      Server port (default: 8000 or PORT env var)
```

## Deployment

- **Backend**: See [../DEPLOYMENT.md](../DEPLOYMENT.md) for nginx deployment guide
- **Frontend**: See [FRONTEND_DEPLOYMENT.md](./FRONTEND_DEPLOYMENT.md) for Vercel deployment

## Troubleshooting

### "Claude Agent SDK not installed"
```bash
pip install claude-agent-sdk
```

### "RAPID_API_KEY not found"
Twitter tools require RapidAPI subscription:
1. Go to https://rapidapi.com/davethebeast/api/twitter283
2. Subscribe and get API key
3. Add to `.env`: `RAPID_API_KEY=xxx`

### "Skill directory not found" (v3)
Ensure the skill exists:
```bash
ls .claude/skills/vc-research/
```

### Test MCP Servers Directly
```bash
# Test Twitter MCP
python twitter_mcp.py --test @username

# Test Firecrawl MCP
python firecrawl_mcp.py --test https://example.com
```
