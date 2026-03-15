# xAI Function Calling Test Scripts

This directory contains test scripts for the xAI SDK function calling implementation.

## Test Scripts

### 1. `test_local_tools.py`
A comprehensive test script that tests each tool function locally with sample data.

**Usage:**
```bash
python test_local_tools.py
```

**What it tests:**
- `get_twitter_profile` - Fetches Twitter profile information
- `get_twitter_following` - Gets following list (with oldest_first for founder detection)
- `get_twitter_tweets` - Retrieves recent tweets
- `scrape_website` - Scrapes website content

**Sample profiles tested:**
- @elonmusk - General profile test
- @sama - Following and tweets test
- @doppler_fi - Crypto project comprehensive test

### 2. `test_xai_function_calls.py`
Simulates exactly how xAI SDK calls functions during a conversation.

**Usage:**
```bash
python test_xai_function_calls.py
```

**What it demonstrates:**
- How xAI sends function calls with JSON arguments
- The exact format of function execution
- Error handling for various failure scenarios
- A complete research workflow simulation

### 3. `xai_mcp_test_sdk.py`
The main xAI SDK integration with function calling support.

**Usage:**
```bash
# Research a specific Twitter profile
python xai_mcp_test_sdk.py doppler_fi

# Use default test profile
python xai_mcp_test_sdk.py
```

## Required Environment Variables

Add these to your `.env` file:

```env
# xAI API Key (required)
XAI_API_KEY=your_xai_api_key_here

# Tool API Keys
RAPID_API_KEY=your_rapid_api_key  # For Twitter tools
FIRECRAWL_API_KEY=your_firecrawl_key  # For web scraping
```

## How Function Calling Works

1. **xAI SDK sends a function call** with:
   - Function name (e.g., "get_twitter_profile")
   - Arguments as JSON string (e.g., '{"username": "doppler_fi"}')

2. **Local execution**:
   - Parse the JSON arguments
   - Call the corresponding tool function
   - Return results as a dictionary

3. **Results sent back to xAI**:
   - xAI receives the tool results
   - Continues conversation with new information
   - May request additional tool calls

## Example Function Call Flow

```python
# xAI requests Twitter profile
{
    "function": {
        "name": "get_twitter_profile",
        "arguments": '{"username": "doppler_fi"}'
    }
}

# Local execution
result = tools.get_twitter_profile(username="doppler_fi")

# Result sent back to xAI
{
    "name": "Doppler",
    "username": "doppler_fi",
    "bio": "DeFi yield automation...",
    "followers_count": 12500,
    ...
}
```

## Debugging

- Logs are saved to `logs/` directory
- Debug responses saved to `debug/` directory
- Check console output for detailed execution traces

## Notes

- Function calls come as complete chunks when streaming (not streamed incrementally)
- The model may make multiple iterations of tool calls
- Error handling is important - failed tools should return error dictionaries
- All tools execute locally using configured API keys