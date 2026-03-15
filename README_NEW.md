# OpenAI MCP Research System

A two-component system for AI-powered research on blockchain/crypto projects:

## Components

### 1. MCP Server (`mcp_server/`)
A Model Context Protocol server providing Twitter and web tools:
- Runs independently on port 8000
- Provides 6 tools via FastMCP/SSE
- No modifications needed for research tasks

**Quick Start:**
```bash
cd mcp_server
pip install -r requirements.txt
python main.py
```

### 2. Research Agent (`research_agent/`)
Command-line tool for automated project research:
- Uses OpenAI O3 API with MCP tools
- Integrates with Notion for project management
- Creates comprehensive research reports

**Quick Start:**
```bash
cd research_agent
pip install -r requirements.txt
python research_agent.py --dry-run
```

## Project Structure
```
openai_mcp/
├── mcp_server/          # MCP tool server
│   ├── main.py          # Server entry point
│   ├── tools.py         # Tool implementations
│   ├── tests/           # Server tests
│   └── requirements.txt
│
├── research_agent/      # Research automation
│   ├── research_agent.py # Main agent script
│   ├── examples/        # API usage examples
│   └── requirements.txt
│
├── shared/              # Shared configurations
│   ├── .env            # Environment variables
│   └── requirements.txt # All dependencies
│
├── docs/               # Documentation
├── logs/               # Log files
└── reference_project/  # Reference implementation
```

## Setup

1. **Environment Variables**
   Copy `.env.example` to `.env` and fill in:
   ```
   # For Research Agent
   OPENAI_API_KEY=sk-xxx
   NOTION_API_KEY=ntn_xxx
   NOTION_DATABASE_ID=xxx
   
   # For MCP Server
   RAPID_API_KEY=xxx
   FIRECRAWL_API_KEY=xxx
   ```

2. **Install Dependencies**
   ```bash
   # For both components
   pip install -r shared/requirements.txt
   
   # Or individually
   cd mcp_server && pip install -r requirements.txt
   cd research_agent && pip install -r requirements.txt
   ```

3. **Run the System**
   ```bash
   # Terminal 1: Start MCP Server
   cd mcp_server
   python main.py
   
   # Terminal 2: Run Research Agent
   cd research_agent
   python research_agent.py
   ```

## Documentation
- [MCP Server Documentation](mcp_server/README.md)
- [Research Agent Documentation](research_agent/README.md)
- [Implementation Plan](docs/DEEP_RESEARCH_IMPLEMENTATION_PLAN.md)