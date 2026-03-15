# End-to-End Testing Instructions

## Running a Single Project Test

To test the new structured markdown format with a single project, use the test script:

### Basic Usage:

```bash
# Test with default project (ZarkLab)
python test_single_project.py

# Test with a specific Twitter handle
python test_single_project.py pumpdotfun
python test_single_project.py @worldcoin
```

### What the Test Does:

1. **Initializes the Research Agent** with your API keys
2. **Researches the specified project** using the AI
3. **Logs everything** to detailed log files
4. **Shows you where logs are saved** for debugging
5. **Displays a preview** of the research report
6. **Checks if AI used the new format** (structured markdown)
7. **Tests Notion block conversion** to ensure formatting works
8. **Saves the full report** for inspection

### Log File Locations:

- **Main logs**: `logs/research_agent_YYYYMMDD_HHMMSS.log`
- **Project-specific logs**: `logs/projects_YYYYMMDD/test_project_*.log`
- **Full API response**: Included in project log with complete details

### What to Look For:

1. **Structured Format Check**:
   - ✅ Good: "AI returned structured format!"
   - ⚠️  Bad: "AI returned old format"

2. **Metadata Extraction**:
   - Should show Priority and Stage from META_ fields

3. **Section Count**:
   - Should show 8 sections (Overview, Technology, Team, etc.)

4. **Notion Blocks**:
   - Should generate multiple block types (callout, heading_1, paragraph, etc.)

### Debugging:

If the AI doesn't use the new format:

1. Check the project log file for the exact prompt sent
2. Look for any errors in the API response
3. Verify the system prompt includes the structured format instructions

### Full Testing Workflow:

```bash
# 1. Run the test
python test_single_project.py pumpdotfun

# 2. Check the output for structured format confirmation

# 3. Review the saved report file (test_report_*.md)

# 4. Check the detailed logs if needed
# Look in logs/projects_YYYYMMDD/ for the full API conversation

# 5. Optionally run the full agent to see Notion upload
python research_agent.py --database production --limit 1
```

### Environment Variables Required:

Make sure these are set in your `.env` file:
- `OPENAI_API_KEY`
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`
- `MCP_SERVER_URL` (if not using default)

### Sample Output:

```
================================================================================
RESEARCH AGENT - SINGLE PROJECT TEST
================================================================================

Project: Test Project - @pumpdotfun
Twitter: @pumpdotfun
Time: 2024-01-27 14:30:00

📁 Log Files Location:
   Main logs: logs/
   Project logs: logs/projects_20240127/

🔧 Initializing Research Agent...
✅ Research Agent initialized successfully

🔍 Starting research for @pumpdotfun...
   (This may take 2-5 minutes depending on the project complexity)

✅ Research completed in 125.3 seconds

📄 Full API response logged to:
   logs/projects_20240127/test_project_143245.log
   Size: 285.7 KB

📊 Research Content Preview:
--------------------------------------------------------------------------------
✅ AI returned structured format!
   Priority: High
   Stage: Pre-Seed/Seed
   Sections found: 8
     - Project Overview
     - Technology & Products
     - Team & Backers
     - Market & Traction
     - Competitive Landscape
     - Timeline & Milestones
     - Risks & Challenges
     - Conclusion & Outlook
```