import os
import json
import logging
import asyncio
from datetime import datetime

# Unset proxy environment variables to prevent httpx/openai library conflicts
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client
from dotenv import load_dotenv

# --- Enhanced Logging Configuration ---
log_file = 'api_test_gemini_native_run.log'
detailed_log_file = 'api_test_gemini_detailed.log'

# Create formatters for different log levels
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
console_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
)

# Configure root logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Clear existing handlers
logger.handlers = []

# File handler for detailed logging
file_handler = logging.FileHandler(detailed_log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(detailed_formatter)
logger.addHandler(file_handler)

# Console handler for important messages
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Silence noisy loggers but keep MCP-related ones
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Enable detailed logging for MCP and Gemini
logging.getLogger("mcp").setLevel(logging.DEBUG)
logging.getLogger("google.genai").setLevel(logging.DEBUG)

# Load environment variables
load_dotenv()

# --- Configuration ---
logger.info("🚀 Loading configuration from .env file...")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MCP_SERVER_URL_RAW = os.environ.get("MCP_SERVER_URL")

# --- Validation ---
if not GEMINI_API_KEY:
    logger.error("❌ CRITICAL: Please set your GEMINI_API_KEY in a .env file.")
    exit()

if not MCP_SERVER_URL_RAW:
    logger.error("❌ CRITICAL: Please set your MCP_SERVER_URL in a .env file.")
    exit()

# Use the SSE URL directly (keep /sse suffix for SSE transport)
MCP_SSE_URL = MCP_SERVER_URL_RAW.rstrip('/')
if not MCP_SSE_URL.endswith('/sse'):
    MCP_SSE_URL += '/sse'

logger.info(f"🔗 MCP SSE URL: {MCP_SSE_URL}")

# --- Native Gemini Client Initialization ---
logger.info("🧠 Initializing native Gemini client...")
client = genai.Client(api_key=GEMINI_API_KEY)

# Use the thinking model for complex research tasks with deep research configuration
THINKING_MODEL = "gemini-2.5-pro-preview-06-05"  # Latest thinking model
logger.info(f"🤖 Using Thinking Model: {THINKING_MODEL}")

# --- System & User Messages ---
system_message = """
You are an advanced AI analyst tasked with producing thorough, citation‑rich research briefs on blockchain / crypto projects.
A dynamic MCP server exposes a variable toolset (e.g., social‑media APIs, web search, website scrapers, summarizers).
Your mission is to discover those tools at run‑time, orchestrate them intelligently in one reasoning session, gather all material facts, and deliver a structured, in‑depth report—while keeping token usage efficient.

────────────────────────────────────────

CORE OBJECTIVES
────────────────────────────────────────

Comprehensiveness Cover the project’s identity, technology, products, roadmap, team, investors, community traction, and risks.

Source‑Driven Every factual claim must trace to at least one tool output (use the provided citation format).

Token Discipline Avoid ingesting unnecessary bulk (images, full HTML blobs, huge docs) by preferring built‑in summary or slimming flags when offered.

Single‑Round Completion All discovery and reasoning happens inside this single API call; finish only when confident no major information gap remains.

Depth & Narrative Target ~1 500–2 000 output tokens; expand bullet points into well‑supported prose where helpful.

────────────────────────────────────────

ADAPTIVE RESEARCH WORKFLOW
────────────────────────────────────────
0 · Tool Discovery
  • Invoke the tool‑catalog action (e.g., mcp_list_tools) to learn which functions exist and which size‑reduction flags they support.

1 · Primary Profile Identification
  • If the user provides a handle, fetch that social profile first via twitter profile tool.
  • Check whether the profile’s “website/URL” field is populated.
  • If absent or empty, fall back to web search to locate an official site or docs.
  • If both fail, proceed using the profile itself plus third‑party coverage.

2 · Network & Team Extraction
  • From the main profile and site, harvest the names / handles of founders, early advisors, investors, and affiliated projects.
  • KEY INSIGHT: If no team profiles found via twitter profile, retrieve profile following with oldest first - inspect the list for POTENTIAL TEAM MEMBERS - SPECULATE IF YOU NEED.
  • For each core team member:
    – Retrieve their Twitter/X profile and build it into the report. 
    - Perform research on the team member via their tweets or using the search tool.

3 · Project Activity & Milestones
  • Pull recent posts (tweets, blog RSS, GitHub commits—whatever tools exist) to surface launch dates, audits, releases, TVL metrics, etc.

4 · Official Resources
  • When a docs or website link is known, scrape it with image‑stripping / readability / summary options if offered. DO NOT initiate web scraping and simply skip if the URL's domain points to https://t.co 
  • If no URL was found in Step 1, perform a web search for ProjectName + “official site” or “docs” and scrape the best candidate(s).

5 · Independent Context
  • Run a web‑search tool for “ProjectName” plus modifiers such as “roadmap”, “funding”, “controversy”, etc.
  • Iterate through search‑result pages until two successive pages yield no materially new facts or citations.

5 · Technology and product
  • Based on the search / profile results, perform in-depth research on the technology and product - iteratively perform additional searches.
  • Iterate through search‑result pages until two successive pages yield no materially new facts or citations.

6 · Iterative Deepening
  • After each retrieval, scan for new entities, features, or metrics. This is IMPORTANT. When you retrieve twitter following for teams/projects, they will contain URLs. Pinpoint useful profiles and retrieve their tweets or use the search tool for analysis.
  • Loop back to the toolset to fetch any missing critical evidence (e.g., product/project details, team profiles, backers, etc).

6 · Tool selection rules
  • When search is needed, use the `search_web` tool provided by the MCP server. This tool performs a web search and scrapes the content of the results, providing comprehensive information for analysis.

────────────────────────────────────────
REPORT SYNTHESIS STANDARDS
────────────────────────────────────────
• IMPORTANT - optimize for details - DO NOT SHORTEN THE REPORT. DETAILS MATTER.
• Structure the brief using these headings (minimum and MUST HAVE):  
  1. **Project Overview**  
  2. **Technology & Products**  
  3. **Timeline / Milestones**  
  4. **Team & Backers**  
  5. **Market & Traction**  
  6. **Risks & Challenges**  
  7. **Conclusion / Outlook**  
• Cite every quantitative or specific statement immediately after it.  
• If data conflicts, reconcile or flag uncertainties.  
• Do not speculate beyond evidence.

────────────────────────────────────────
ERROR & EDGE‑CASE HANDLING
────────────────────────────────────────
• If a tool errors, retry once with adjusted arguments (e.g., different limit, corrected handle).  
• If no official site is discoverable, state that clearly and rely on social / third‑party sources.  
• If context length approaches tool or model limits, prioritise summaries over full text and drop low‑value content.

Complete the checklist, then present the report. End of prompt.
"""

user_query = "Research doppler_fi"

def log_interaction(interaction_type: str, data: any, step: str = ""):
    """Enhanced logging for interactions."""
    logger.info(f"🔄 {interaction_type}: {step}")
    logger.debug(f"📊 {interaction_type} Data: {json.dumps(data, indent=2, default=str)}")
    
    # Also write to detailed log file
    with open(detailed_log_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"{interaction_type.upper()}: {step}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n")
        f.write(json.dumps(data, indent=2, default=str))
        f.write(f"\n{'='*80}\n\n")

def log_gemini_response(response: any, step: str = ""):
    """Enhanced logging for Gemini responses."""
    logger.info(f"🧠 Gemini Response: {step}")
    
    # Log detailed response structure
    with open(detailed_log_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"GEMINI RESPONSE: {step}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n")
        
        try:
            if hasattr(response, 'model_dump_json'):
                f.write(response.model_dump_json(indent=2))
            else:
                f.write(json.dumps(response, indent=2, default=str))
        except Exception as e:
            f.write(f"Error serializing response: {e}\n")
            f.write(f"Response type: {type(response)}\n")
            f.write(f"Response attributes: {dir(response)}\n")
            f.write(f"Response str: {str(response)}\n")
        
        f.write(f"\n{'='*80}\n\n")

async def run_gemini_with_mcp_builtin():
    """Run Gemini with built-in MCP support using SSE transport."""
    logger.info("🚀 Starting Gemini with Built-in MCP Support (SSE)...")
    
    try:
        # Connect to MCP server using SSE transport (like OpenAI does)
        logger.info("🔌 Connecting to MCP server via SSE...")
        async with sse_client(MCP_SSE_URL) as (read, write):
            async with ClientSession(read, write) as session:
                logger.info("🤝 Initializing MCP session...")
                log_interaction("MCP_CONNECTION", {"status": "initializing", "url": MCP_SSE_URL}, "SSE Session Start")
                
                await session.initialize()
                log_interaction("MCP_CONNECTION", {"status": "initialized"}, "SSE Session Initialized")
                
                # Get available tools from MCP server
                logger.info("🔍 Discovering MCP tools...")
                mcp_tools = await session.list_tools()
                logger.info(f"✅ Found {len(mcp_tools.tools)} MCP tools")
                
                # Log all available tools
                tools_info = []
                for tool in mcp_tools.tools:
                    tool_info = {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    }
                    tools_info.append(tool_info)
                    logger.info(f"  🛠️  {tool.name}: {tool.description}")
                
                log_interaction("TOOL_DISCOVERY", tools_info, "MCP Tools Discovered")
                
                # Create the prompt
                prompt = f"{system_message}\n\nUser Query: {user_query}"
                
                logger.info(f"🧠 Sending request to {THINKING_MODEL} with MCP session...")
                logger.debug(f"📝 Prompt: {prompt}")
                
                # Define the Google Search tool using the structured types from the SDK
                # This is the key change to ensure compatibility. not supported cannot be combined with MCP
                #google_search_tool = types.Tool(
                #    google_search=types.GoogleSearch()
                #)

                # Combine the MCP session and the structured Google Search tool
                tools_config = [
                    session,            # Pass the MCP session object
                    #google_search_tool, # Pass the structured Google Search tool object
                ]
                
                # The rest of the call remains the same, but uses the new tools_config
                response = await client.aio.models.generate_content(
                    model=THINKING_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=12000,
                        tools=tools_config,  # Use the new combined list of tool objects
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=False
                        ),
                    ),
                )
                
                log_gemini_response(response, "Built-in MCP Response with Automatic Tool Calling")
                
                logger.info("🎯 === GEMINI BUILT-IN MCP RESPONSE ===")
                logger.info(f"🤖 Model: {THINKING_MODEL}")
                logger.info(f"🔬 Research Mode: DEEP RESEARCH with BUILT-IN MCP")

                # Add more detailed logging for failure analysis
                # Log prompt feedback if it exists, as it can contain warnings.
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    logger.warning(f"🚨 Prompt Feedback received: {response.prompt_feedback}")
                
                # Log the response details
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    finish_reason = getattr(candidate, 'finish_reason', 'unknown')
                    logger.info(f"📊 Finish reason: {finish_reason}")

                    # If the finish reason indicates an issue, log the entire candidate object for debugging.
                    # This will give us maximum context on errors like MALFORMED_FUNCTION_CALL.
                    if finish_reason not in [types.FinishReason.STOP, types.FinishReason.MAX_TOKENS]:
                        logger.warning("⚠️ Model stopped for an unusual reason. Logging detailed candidate object:")
                        try:
                            logger.warning(candidate.model_dump_json(indent=2))
                        except Exception as e:
                            logger.error(f"Could not dump candidate to JSON: {e}")
                            logger.warning(str(candidate))
                    
                    if hasattr(candidate, 'content') and candidate.content:
                        for part_idx, part in enumerate(candidate.content.parts):
                            if hasattr(part, 'function_call') and part.function_call:
                                func_call = part.function_call
                                logger.info(f"🔧 Function Call #{part_idx}: {func_call.name}")
                                logger.info(f"   📥 Arguments: {dict(func_call.args)}")
                                
                                # Log the function call
                                log_interaction("FUNCTION_CALL", {
                                    "name": func_call.name,
                                    "arguments": dict(func_call.args),
                                    "part_index": part_idx
                                }, f"MCP Function Call: {func_call.name}")
                                
                            elif hasattr(part, 'text') and part.text:
                                logger.info(f"📝 Text Part #{part_idx}: {part.text[:100]}...")
                
                # Print the final response
                if hasattr(response, 'text') and response.text:
                    logger.info("🎯 === FINAL DEEP RESEARCH RESPONSE ===")
                    logger.info(response.text)
                    
                    # Also log the final response to detailed log
                    with open(detailed_log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"FINAL DEEP RESEARCH RESPONSE\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        f.write(f"{'='*80}\n")
                        f.write(response.text)
                        f.write(f"\n{'='*80}\n\n")
                else:
                    logger.warning("⚠️ No final text response found")
                    logger.debug(f"Response type: {type(response)}")
                    logger.debug(f"Response attributes: {dir(response)}")
                
                return response
                
    except Exception as e:
        logger.critical(f"💥 Critical error in Gemini built-in MCP integration: {e}", exc_info=True)
        log_interaction("ERROR", {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        }, "Critical Error")
        return None

if __name__ == "__main__":
    logger.info("🚀 Starting Gemini Built-in MCP Test...")
    logger.info(f"📝 Detailed logs will be written to: {detailed_log_file}")
    logger.info(f"🧠 Using Thinking Model: {THINKING_MODEL}")
    logger.info(f"🔗 MCP SSE URL: {MCP_SSE_URL}")
    logger.info(f"🔬 Deep Research Mode: ENABLED with BUILT-IN MCP SUPPORT")
    
    try:
        result = asyncio.run(run_gemini_with_mcp_builtin())
        if result:
            logger.info("✅ Deep research completed successfully")
            logger.info(f"📊 Check {detailed_log_file} for complete interaction logs")
        else:
            logger.error("❌ Deep research failed")
    except Exception as e:
        logger.critical(f"💥 Fatal error in main execution: {e}", exc_info=True)
    
    logger.info("🏁 --- Gemini Built-in MCP Test Finished ---") 