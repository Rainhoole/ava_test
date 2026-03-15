# Research Agent - Comprehensive Guide

## Overview
The Research Agent is an advanced command-line tool that performs automated AI research on blockchain/crypto projects using OpenAI's O3/O4 models with MCP (Model Context Protocol) tools. It integrates with Notion databases to pull projects, conduct deep research using Twitter and web data, and creates comprehensive reports with scoring.

## Complete Setup Guide (Mac/Linux)

### Step 1: System Requirements
```bash
# Ensure Python 3.8+ is installed
python3 --version

# Install pip if not present
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py
```

### Step 2: Clone and Setup Project
```bash
# Clone the repository (adjust path as needed)
git clone https://github.com/yourusername/openai_mcp.git
cd openai_mcp

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Mac/Linux

# Install all dependencies
pip install -r requirements.txt
pip install openai notion-client python-dotenv requests
```

### Step 3: Configure Environment Variables
```bash
# Create .env file in project root
cat > .env << 'EOF'
# OpenAI Configuration
OPENAI_API_KEY=sk-xxx          # Your OpenAI API key for O3/O4 access

# Notion Configuration
NOTION_API_KEY=ntn_xxx         # Your Notion integration API key
NOTION_DATABASE_ID=xxx         # Your main Notion database ID
NOTION_DATABASE_ID_EXT=xxx    # Optional: External database for score syncing

# MCP Server Configuration
MCP_SERVER_URL=http://localhost:8000/sse  # MCP server endpoint

# API Keys for MCP Tools
RAPID_API_KEY=xxx              # RapidAPI key for Twitter data
FIRECRAWL_API_KEY=xxx          # Firecrawl API key for web scraping
EOF
```

### Step 4: Notion Database Setup #DO NOT NEED - ALREADY DONE
```bash
# Your Notion database must have these properties:
# 1. Name (title) - Project name
# 2. Twitter (text) - Twitter handle (e.g., @username or username)
# 3. Research Status (multi-select) with options:
#    - not researched
#    - in progress
#    - completed
#    - error
# 4. Summary (text) - Optional project description
# 5. Raw Score (number) - Auto-populated by agent
# 6. Denominator (number) - Auto-populated by agent
# 7. Ava's Priority (select) - Auto-populated by agent
```

### Step 5: Start MCP Server #DO NOT NEED - ALREADY DONE
```bash
# In a separate terminal, start the MCP server first
cd openai_mcp
python main.py
# Server should start on http://localhost:8000
```

### Step 6: Run Research Agent
```bash
# Navigate to research_agent directory
cd research_agent

# Test with dry run first #DO NOT USE
python research_agent.py --dry-run

# Run actual research
# Note if ANY research is conducted - the external facing notion database will also be updated. BE AWARE.
# if a project's research status is "completed" the agent will not research again - toggle it to empty for agent to research again.
python research_agent.py
```

## Complete Command Options Reference

### All Available Options
```bash
python research_agent.py [OPTIONS]

Options:
  --batch-size N        Number of projects to process (default: 10)
  --project-id ID       Research specific project by Notion page ID
  --dry-run            Preview what would be processed without execution
  --sequential         Use sequential processing instead of parallel (parallel is default)
  --workers N          Number of parallel workers (default: 10, max: 10)
  --instant            Use instant processing mode (faster, more expensive)
  --model MODEL        AI model to use: 'o3' (default) or 'o4-mini'
  --override_research  Override early exit for later-stage projects
  --prompt FILE        Path to custom prompt .md file (default: research_agent_prompt.md)
```

### Execution Modes Explained

#### 1. Dry Run Mode (Testing) #DO NOT USE
```bash
# See what projects would be processed
python research_agent.py --dry-run
python research_agent.py --batch-size 10 --dry-run
```

#### 2. Single Project Mode
```bash
# Research specific project by Notion page ID
python research_agent.py --project-id "abc123-def456-789"

# With instant processing
python research_agent.py --project-id "abc123" --instant

# Override funding stage checks - will perform research on later stage deals.
python research_agent.py --project-id "abc123" --override_research
```

#### 3. Batch Parallel Mode (Default)
```bash
# Process 10 projects in parallel (default)
python research_agent.py

# Process 20 projects in parallel with default 10 workers
python research_agent.py --batch-size 20

# Process with custom worker count
python research_agent.py --batch-size 15 --workers 5

# With instant processing (faster, more expensive)
python research_agent.py --batch-size 10 --instant
```

#### 4. Batch Sequential Mode (Legacy)
```bash
# Force sequential processing (not recommended)
python research_agent.py --batch-size 10 --sequential

# Sequential with instant mode
python research_agent.py --batch-size 5 --sequential --instant

# Note: Sequential mode processes one project at a time
# This is slower but may be useful for debugging
```

#### 5. Model Selection
```bash
# Use O3 model (default, most capable)
python research_agent.py --model o3

# Use O4-mini model (faster, lighter)
python research_agent.py --model o4-mini --batch-size 10
```

#### 6. Custom Prompt File
```bash
# Use a custom prompt for specific research focus
python research_agent.py --prompt custom_research_prompt.md

# Custom prompt with specific project
python research_agent.py --project-id "abc123" --prompt detailed_analysis_prompt.md

# Custom prompt for batch processing
python research_agent.py --batch-size 20 --prompt crypto_focused_prompt.md
```

#### 7. Advanced Combinations
```bash
# Maximum speed: parallel (default) + instant + 10 workers
python research_agent.py --batch-size 20 --instant --workers 10

# Maximum cost savings: parallel with flex (default settings)
python research_agent.py --batch-size 20

# Research all later-stage projects too
python research_agent.py --batch-size 10 --override_research
```

### Performance & Cost Comparison

| Mode | 10 Projects Time | Cost | Best For |
|------|-----------------|------|----------|
| Parallel + Flex (default) | ~2-4 min | Low | Standard usage, best balance |
| Parallel + Instant | ~1-2 min | Highest | Urgent research needs |
| Sequential + Flex | ~20-40 min | Lowest | Debugging, single-threaded needs |
| Sequential + Instant | ~15-20 min | High | Single project debugging |

## Processing Modes Deep Dive

### Flex Processing (Default - Cost Optimized)
Flex mode is **enabled by default** and provides significant cost savings at the expense of speed.

```bash
# Flex is ON by default (no flag needed)
python research_agent.py --batch-size 10

# Explicitly disable flex with --instant
python research_agent.py --batch-size 10 --instant
```

**Benefits:**
- 💰 Token costs at Batch API rates (up to 50% savings)
- 🔄 Automatic retry on resource unavailability (3 attempts)
- ⏱️ Extended timeout: 20 minutes per project
- 📊 Same research quality as instant mode

**Trade-offs:**
- 🐢 2-10x slower response times
- ⚠️ Occasional "Resource Unavailable" errors (auto-retried)
- 🔧 Only available for O3 and O4-mini models

### Instant Processing (Speed Optimized)
```bash
# Enable with --instant flag
python research_agent.py --batch-size 10 --instant --parallel
```

**Benefits:**
- ⚡ Fastest response times
- 🎯 Consistent availability
- ⏱️ 15-minute timeout per project

**Trade-offs:**
- 💸 Higher token costs
- ❌ No automatic retry on 429 errors

### When to Use Each Mode

| Use Flex (Default) | Use Instant |
|-------------------|-------------|
| ✅ Overnight/weekend runs | ✅ Time-critical research |
| ✅ Large batches (10+ projects) | ✅ Debugging single projects |
| ✅ Cost-sensitive operations | ✅ Production with SLA requirements |
| ✅ Research backlogs | ✅ Real-time analysis needs |

## How It Works - Technical Flow

### 1. Project Discovery
The agent queries your Notion database for projects to research:
```python
# Filters for projects with these statuses:
- Empty "Research Status" (new projects)
- "not researched" status
- "error" status (retry failed projects)
- "in progress" > 2 hours (stuck projects)
```

### 2. Project Filtering
- **Twitter Requirement**: Only processes projects with Twitter handles
- **Sorting**: Newest projects first (by last_edited_time)
- **Stuck Detection**: Auto-retries projects stuck "in progress" > 2 hours

### 3. Research Execution
For each project:
```
1. Update status → "in progress"
2. Create isolated OpenAI client (prevents context overflow)
3. Execute research with query: "Research twitter profile {handle}"
4. Use MCP tools:
   - get_twitter_profile
   - get_twitter_following
   - get_twitter_tweets
   - bulk_get_twitter_profiles
   - scrape_website
   - search_web
5. Generate comprehensive report
6. Extract scoring (X/26 points)
7. Upload to Notion as new page
8. Update status → "completed" or "error"
9. Update Raw Score and Denominator fields
```

### 4. Context Isolation Architecture
Each research task creates its own OpenAI client:
```python
# Prevents context accumulation in parallel processing
openai_client = OpenAI(api_key=self.openai_api_key, timeout=timeout)
```
This enables processing 10+ projects in parallel without context errors.

### 5. Error Handling

| Error Type | Behavior |
|------------|----------|
| 500/424 API errors | Silent skip, revert status, exit after 5 occurrences |
| 502/503 Infrastructure | Retry with backoff (60s, 120s, 180s) |
| 429 Resource Unavailable | Retry with backoff (30s, 60s, 90s) in flex mode |
| MCP timeouts | Continue with partial data |
| Missing Twitter handle | Create error report, mark as error |
| Other exceptions | Upload error report to Notion |

## Output & Reports

### Report Structure
Each research report includes:
1. **Project Overview** - Basic information and summary
2. **Founder Analysis** - Team background and credibility
3. **Project Evaluation** - Technology and market position
4. **Community & Traction** - Social metrics and engagement
5. **Token Analysis** - Tokenomics and distribution
6. **Risk Assessment** - Key risks and red flags
7. **Final Verdict** - Score (X/26) and priority (High/Medium/Low)

### Notion Integration
- **New Page Created**: "{Project Name} - Research Report"
- **Title Format**: "🤖 Ava's Report"
- **Timestamp**: Eastern Time (ET)
- **Attribution**: "Generated by Ava's Research Agent Alice"
- **Auto-populated Fields**:
  - Raw Score (numeric)
  - Denominator (numeric)
  - Ava's Priority (select)
  - Research Status (multi-select)

### Scoring System
- **Total Points**: 26 possible
- **Priority Levels**:
  - High: Strong investment potential
  - Medium: Promising with caveats
  - Low: Significant concerns
- **Score -1**: Indicates scoring extraction failed

## Logs and Monitoring

### Log Structure
```
logs/
├── research_agent_YYYYMMDD_HHMMSS.log    # Main execution log
└── projects_YYYYMMDD/                    # Daily project logs
    ├── ProjectName_TwitterHandle_HHMMSS_Worker-0.log
    ├── ProjectName_TwitterHandle_HHMMSS_Worker-1.log
    └── ...
```

### Log Levels
- **Main Log**: High-level execution flow, summaries
- **Project Logs**: Detailed API calls, responses, step-by-step analysis

### What's Logged
```
✅ Project discovery and filtering
✅ API request/response details
✅ MCP tool calls and results
✅ Web search queries and costs
✅ Token usage and caching
✅ Error stack traces
✅ Thread coordination (parallel mode)
✅ Performance metrics
```

### Reading Logs
```bash
# Monitor main log in real-time
tail -f logs/research_agent_*.log

# View specific project log
cat logs/projects_*/ProjectName_*.log

# Search for errors
grep -r "ERROR" logs/

# Find completed research URLs
grep "Research complete:" logs/research_agent_*.log
```

## Troubleshooting

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "MCP server not responding" | Start MCP server: `python main.py` |
| "Missing required environment variables" | Check .env file has all required keys |
| "No Twitter handle provided" | Add Twitter handle to Notion project |
| "429 Resource Unavailable" | Normal in flex mode, auto-retries 3x |
| "500/424 errors" | API overload, wait and retry |
| "Context length exceeded" | Parallel processing prevents this |
| Projects stuck "in progress" | Auto-detected and retried after 2 hours |

### Quick Fixes
```bash
# Reset stuck project status
python research_agent.py --project-id "stuck-project-id" --override_research

# Test single project with verbose logging
python research_agent.py --project-id "test-id" --instant

# Verify configuration
python research_agent.py --dry-run --batch-size 1
```

## Advanced Features

### Custom Prompt Files
Create specialized prompts for different research focuses:
```bash
# Create a custom prompt file
cp research_agent_prompt.md crypto_deep_dive_prompt.md
# Edit the file to customize research focus
vim crypto_deep_dive_prompt.md

# Use the custom prompt
python research_agent.py --prompt crypto_deep_dive_prompt.md
```

**Use Cases for Custom Prompts:**
- Different scoring criteria for specific project types
- Focused analysis on technical aspects vs. business aspects
- Custom report formats for different stakeholders
- Testing prompt variations for better results

### Override Research Flag
Forces complete research even for later-stage projects:
```bash
python research_agent.py --override_research --batch-size 10
```

### External Database Sync
If `NOTION_DATABASE_ID_EXT` is set, scores are synced to both databases.

### Automatic Retries
- Projects with "error" status are automatically retried
- Projects stuck "in progress" > 2 hours are retried
- 429 errors retry 3x with exponential backoff (flex mode)
- 502/503 errors retry 3x with 60s+ backoff

### Safety Features
- Exits after 5 consecutive 500/424 errors
- Thread-safe score updates
- Isolated OpenAI clients per task
- Automatic status reversion on failures

## Best Practices

1. **Start Small**: Test with `--dry-run` and single projects first
2. **Use Parallel + Flex**: Best balance of speed and cost
3. **Monitor Logs**: Check project logs for detailed debugging
4. **Batch Wisely**: 10-15 projects optimal for parallel processing
5. **Schedule Runs**: Use cron for overnight batch processing
6. **Handle Errors**: Projects with errors auto-retry on next run

## Example Workflows

### Daily Research Pipeline
```bash
# Morning: Process new high-priority projects fast
python research_agent.py --batch-size 10 --instant

# Afternoon: Process medium batch with default settings
python research_agent.py --batch-size 20

# Overnight: Process large backlog with max parallelism
python research_agent.py --batch-size 50 --workers 10
```

### Debug Workflow
```bash
# 1. Check what would run
python research_agent.py --dry-run

# 2. Test single project
python research_agent.py --project-id "test-id" --instant

# 3. Check logs
cat logs/projects_*/test-id_*.log

# 4. Run small batch
python research_agent.py --batch-size 3 --instant

# 5. Test with custom prompt
python research_agent.py --project-id "test-id" --prompt test_prompt.md --dry-run
```