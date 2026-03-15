# Python Tools Test Suite

This directory contains comprehensive tests for all Python tool implementations based on the JavaScript tools from `tools.js`.

## 📋 Test Files

### Individual Tool Tests
- **`test_twitter_profile.py`** - Tests Twitter profile lookup functionality
- **`test_twitter_following.py`** - Tests Twitter following list retrieval
- **`test_twitter_tweets.py`** - Tests Twitter tweets fetching
- **`test_web_scraping.py`** - Tests web scraping via Firecrawl
- **`test_web_search.py`** - Tests web search via Firecrawl
- **`test_bulk_twitter.py`** - Tests bulk Twitter profile retrieval

### Master Test Runner
- **`run_all_tests.py`** - Runs all tests sequentially with summary

## 🔧 Setup

### 1. Install Dependencies
```bash
pip install -r ../requirements.txt
```

### 2. Environment Variables
Create a `.env` file in the project root with:
```env
# Twitter API (via RapidAPI)
RAPID_API_KEY=your_rapidapi_key_here

# Firecrawl API
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
```

### 3. Get API Keys

#### RapidAPI Key (for Twitter tools)
1. Go to [RapidAPI](https://rapidapi.com/)
2. Sign up/login
3. Subscribe to [Twitter API v2](https://rapidapi.com/Glavier/api/twitter135/)
4. Copy your API key

#### Firecrawl API Key (for web scraping/search)
1. Go to [Firecrawl](https://firecrawl.dev/)
2. Sign up for an account
3. Get your API key from the dashboard

## 🚀 Running Tests

### Run All Tests
```bash
python tests/run_all_tests.py
```

### Run Individual Tests
```bash
# Twitter profile lookup
python tests/test_twitter_profile.py

# Twitter following
python tests/test_twitter_following.py

# Twitter tweets
python tests/test_twitter_tweets.py

# Web scraping
python tests/test_web_scraping.py

# Web search
python tests/test_web_search.py

# Bulk Twitter profiles
python tests/test_bulk_twitter.py
```

## 📊 Test Coverage

### Twitter API Tools (via RapidAPI)
- ✅ **Profile Lookup** - Get detailed user profiles
- ✅ **Following Lists** - Retrieve who a user follows (with pagination)
- ✅ **Tweet Retrieval** - Fetch recent tweets from users
- ✅ **Bulk Profiles** - Get multiple profiles by User IDs

### Web Tools (via Firecrawl)
- ✅ **Web Scraping** - Extract content from URLs as markdown
- ✅ **Web Search** - Search the web with content extraction

## 🧪 Test Cases

### Twitter Profile Tests
- Valid usernames (elonmusk, OpenAI, sama)
- Invalid/non-existent usernames
- Usernames with @ prefix
- Error handling

### Twitter Following Tests
- Users with reasonable following counts
- Users with massive following counts (>5000, should skip)
- Founders-only mode (oldest 50 followings)
- Private profiles
- Non-existent users

### Twitter Tweets Tests
- Various users with different tweet volumes
- Different limits (5, 10, 15, 50 tweets)
- Non-existent users
- Error handling

### Web Scraping Tests
- Popular websites (OpenAI, Firecrawl, Example.com)
- Test pages (httpbin.org/html)
- Invalid URLs
- Content validation (headers, links, formatting)

### Web Search Tests
- Common queries with different limits
- Content inclusion vs. metadata only
- Search result validation
- Error handling for invalid queries

### Bulk Twitter Tests
- Small batches (1-5 profiles)
- Empty lists (should error)
- Too many IDs (>100, should error)
- Invalid User IDs
- Valid known User IDs

## 📈 Expected Output

Each test provides detailed output including:
- ✅ Success indicators
- ❌ Error messages with details
- 📊 Data summaries (counts, lengths, etc.)
- 🔍 Sample data previews
- ⚠️ Warnings for edge cases

## 🔍 Debugging

### Common Issues
1. **API Key Missing**: Check your `.env` file
2. **Rate Limiting**: Twitter API has rate limits
3. **Network Issues**: Some tests require internet connectivity
4. **Invalid Data**: Some test cases intentionally test error conditions

### Verbose Output
All tests include detailed logging to help debug issues:
- API request details
- Response parsing
- Error messages with context
- Data validation results

## 🎯 Integration with MCP

These tools are designed to be integrated into the MCP (Model Context Protocol) server as the intelligent backend for the `search` and `fetch` tools required by Deep Research API.

The agent proxy pattern allows:
- **Search tool** → Routes to appropriate specialized tools
- **Fetch tool** → Retrieves cached results from search operations
- **Compliance** → Satisfies Deep Research's tool requirements
- **Flexibility** → Easy to extend with new specialized tools 