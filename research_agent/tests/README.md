# Research Agent Tests

This directory contains tests for the Research Agent, focusing on Notion integration without requiring OpenAI API calls.

## Test Structure

```
tests/
├── notion/                 # Notion-specific tests
│   └── test_notion_integration.py
├── data/                  # Mock data for testing
│   ├── mock_research_data.json
│   ├── mock_research_minimal.json
│   └── mock_research_error.json
└── unit/                  # Unit tests (future)
```

## Running Tests

### 1. Test Notion Connection
```bash
cd research_agent/tests/notion
python test_notion_integration.py --list-items
```

### 2. Test Reading Specific Item
```bash
python test_notion_integration.py --read-item [PAGE_ID]
```

### 3. Test Updating with Mock Research
```bash
python test_notion_integration.py --update-item [PAGE_ID]
```

### 4. Test Complete Workflow
```bash
python test_notion_integration.py --test-workflow
# Or with specific page:
python test_notion_integration.py --test-workflow --page-id [PAGE_ID]
```

## Required Notion Schema

Before running tests, ensure your Notion database has these properties:

| Property | Type | Options/Format |
|----------|------|----------------|
| Name | Title | Project name |
| Research Status | Multi-select | not researched, in progress, completed, error |
| Research Date | Date | ISO format |
| Research Summary | Rich Text | Max 2000 chars |

## Test Scenarios

### 1. Basic Operations
- List database items
- Read item properties
- Update status fields

### 2. Research Updates
- Update existing items (NOT create new)
- Append research content as blocks
- Update multiple properties atomically

### 3. Error Handling
- Invalid page IDs
- Missing properties
- Content size limits

## Mock Data

Three mock research scenarios are provided:

1. **Full Research** (`mock_research_data.json`)
   - Complete research report with all sections
   - Demonstrates full capability

2. **Minimal Research** (`mock_research_minimal.json`)
   - Brief report for testing basic updates
   - Minimal content

3. **Error Research** (`mock_research_error.json`)
   - Simulates research failures
   - Tests error handling

## Environment Setup

The tests use environment variables from the parent `.env`:
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`

No OpenAI API key is required for these tests.

## Debugging

Enable verbose logging:
```bash
export LOG_LEVEL=DEBUG
python test_notion_integration.py --test-workflow
```

Check Notion directly to verify updates are applied correctly.