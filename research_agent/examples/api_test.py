import os
import json
import logging
import re

# Unset proxy environment variables to prevent httpx/openai library conflicts
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from openai import OpenAI
from dotenv import load_dotenv

# --- Logging Configuration ---
# Set up a logger to write to a file with detailed information
log_file = 'api_test_run.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'), # Use UTF-8 encoding
        logging.StreamHandler() # Also print to console
    ]
)
# Silence the noisy httpx logger for cleaner console output
logging.getLogger("httpx").setLevel(logging.WARNING)


# Load environment variables from a .env file
load_dotenv()

# --- Configuration ---
logging.info("Loading configuration from .env file...")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MCP_SERVER_URL_RAW = os.environ.get("MCP_SERVER_URL")

# --- Validation and Cleanup ---
if not OPENAI_API_KEY:
    logging.error("CRITICAL: Please set your OPENAI_API_KEY in a .env file.")
    exit()

if not MCP_SERVER_URL_RAW:
    logging.error("CRITICAL: Please set your MCP_SERVER_URL in a .env file.")
    exit()

# Clean up the MCP server URL
mcp_server_url = MCP_SERVER_URL_RAW
logging.info(f"Using cleaned MCP Server URL: {mcp_server_url}")

# --- OpenAI Client Initialization ---
# Initialize the client directly. Proxy environment variables have been cleared.
logging.info("Initializing OpenAI client...")
client = OpenAI(api_key=OPENAI_API_KEY)

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
  • When search is needed, prefer the built-in web_search tool for the first sweep.
  • If returned data is too shallow for you to perform a institutional level research, call the search tool provided by the mcp server. 

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
user_query = "Research twitter profile leapxpert"
logging.info("System and user messages prepared.")

# --- API Call ---
logging.info("Sending request to the Responses API with model o3")
try:
    response = client.responses.create(
      model="o3",
      input=[
        {"role": "developer", "content": [{"type": "input_text", "text": system_message}]},
        {"role": "user", "content": [{"type": "input_text", "text": user_query}]}
      ],
      tools=[
        {"type": "web_search_preview"},
        {
          "type": "mcp",
          "server_label": "research_tools",
          "server_url": mcp_server_url,
          "require_approval": "never"
        }
      ],
      reasoning={"effort": "high"},
    )

    # Log the entire raw response object to the file for deep debugging
    with open(log_file, 'a', encoding='utf-8') as f:  # Use UTF-8 encoding
        f.write("\n=== COMPLETE RAW API RESPONSE OBJECT ===\n")
        try:
            f.write(response.model_dump_json(indent=2))
        except UnicodeEncodeError as e:
            # If there's still a Unicode issue, write a safe version
            f.write(f"Unicode encoding error when writing response: {e}\n")
            f.write("Response object type: " + str(type(response)) + "\n")
            f.write("Response attributes: " + str(dir(response)) + "\n")
        f.write("\n=== END COMPLETE RAW API RESPONSE OBJECT ===\n\n")
    logging.info(f"Raw API response has been written to {log_file}")

    # --- Log Response Metadata ---
    logging.info("=== RESPONSE METADATA ===")
    logging.info(f"Response ID: {getattr(response, 'id', 'N/A')}")
    logging.info(f"Model: {getattr(response, 'model', 'N/A')}")
    logging.info(f"Usage: {getattr(response, 'usage', 'N/A')}")
    logging.info(f"Total Steps: {len(response.output)}")
    
    # Log step types summary
    step_types = {}
    for step in response.output:
        step_types[step.type] = step_types.get(step.type, 0) + 1
    logging.info(f"Step Types Summary: {step_types}")

    # --- Inspecting Intermediate Steps ---
    logging.info("=== DETAILED STEP-BY-STEP ANALYSIS ===")
    mcp_calls_count = 0
    tool_results_count = 0
    
    for i, step in enumerate(response.output):
        step_info = f">>> Step {i+1}/{len(response.output)}: {step.type.upper()} <<<"
        logging.info(step_info)
        
        # Log the raw step data to the file with safe encoding
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{step_info}\n")
            f.write("--- Raw Step Data ---\n")
            try:
                f.write(step.model_dump_json(indent=2))
            except UnicodeEncodeError as e:
                f.write(f"Unicode encoding error for step {i+1}: {e}\n")
                f.write(f"Step type: {step.type}\n")
                f.write(f"Step attributes: {str(dir(step))}\n")
            f.write("\n--- End Raw Step Data ---\n\n")

        if step.type == "reasoning":
            logging.info("  📝 REASONING STEP:")
            for j, s in enumerate(step.summary):
                logging.info(f"    {j+1}. {s.text}")
        
        elif step.type == "mcp_call":
            mcp_calls_count += 1
            logging.info(f"  🔧 MCP TOOL CALL #{mcp_calls_count}:")
            logging.info(f"    Server Label: {step.server_label}")
            logging.info(f"    Tool Name: {step.name}")
            logging.info(f"    Tool Call ID: {getattr(step, 'tool_call_id', 'N/A')}")
            
            # Log arguments in detail
            logging.info("    Arguments:")
            if isinstance(step.arguments, dict):
                for key, value in step.arguments.items():
                    logging.info(f"      {key}: {value}")
            else:
                logging.info(f"      Raw arguments: {step.arguments}")
            
            # Log any additional MCP call metadata
            for attr in dir(step):
                if not attr.startswith('_') and attr not in ['type', 'server_label', 'name', 'arguments', 'tool_call_id']:
                    try:
                        value = getattr(step, attr)
                        if not callable(value):
                            logging.info(f"    {attr}: {value}")
                    except:
                        pass

        elif step.type == "tool_result":
            tool_results_count += 1
            logging.info(f"  📊 TOOL RESULT #{tool_results_count}:")
            logging.info(f"    Tool Name: {step.tool_name}")
            logging.info(f"    Tool Call ID: {step.tool_call_id}")
            logging.info(f"    Is Error: {getattr(step, 'is_error', 'N/A')}")
            
            # Parse and log the result in detail
            logging.info("    Result Content:")
            try:
                result_data = json.loads(step.result)
                logging.info("      Parsed JSON Result:")
                result_json_str = json.dumps(result_data, indent=6)
                for line in result_json_str.split('\n'):
                    logging.info(f"      {line}")
                
                # If it's our search/fetch result, log specific fields
                if isinstance(result_data, dict):
                    if 'results' in result_data:
                        logging.info(f"      Search Results Count: {len(result_data['results'])}")
                        for idx, result in enumerate(result_data['results']):
                            logging.info(f"        Result {idx+1}: ID={result.get('id', 'N/A')}, Title='{result.get('title', 'N/A')}'")
                    elif 'id' in result_data and 'title' in result_data:
                        logging.info(f"      Document Retrieved: ID={result_data['id']}, Title='{result_data['title']}'")
                        logging.info(f"      Document Text Length: {len(result_data.get('text', ''))}")
                        
            except (json.JSONDecodeError, TypeError):
                logging.info(f"      Raw Result: {step.result}")
            
            # Log any additional tool result metadata
            for attr in dir(step):
                if not attr.startswith('_') and attr not in ['type', 'tool_name', 'tool_call_id', 'result', 'is_error']:
                    try:
                        value = getattr(step, attr)
                        if not callable(value):
                            logging.info(f"    {attr}: {value}")
                    except:
                        pass

        elif step.type == "final_answer":
            logging.info("  ✅ FINAL ANSWER:")
            final_content = step.content[0]
            answer_preview = final_content.text[:200] + "..." if len(final_content.text) > 200 else final_content.text
            logging.info(f"    Answer Preview: {answer_preview}")
            logging.info(f"    Full Answer Length: {len(final_content.text)} characters")
            
            if final_content.annotations:
                logging.info(f"    Citations Count: {len(final_content.annotations)}")
                for ann_idx, annotation in enumerate(final_content.annotations):
                    logging.info(f"      Citation {ann_idx+1}:")
                    logging.info(f"        Title: {annotation.title}")
                    logging.info(f"        URL: {annotation.url}")
                    if hasattr(annotation, 'excerpt'):
                        logging.info(f"        Excerpt: {getattr(annotation, 'excerpt', 'N/A')}")
        
        elif step.type == "web_search_call":
            logging.info("  🌐 WEB SEARCH CALL:")
            if hasattr(step, 'action') and isinstance(step.action, dict):
                logging.info(f"    Query: {step.action.get('query', 'N/A')}")
            if hasattr(step, 'status'):
                logging.info(f"    Status: {step.status}")
            # Log any additional web search metadata
            for attr in dir(step):
                if not attr.startswith('_') and attr not in ['type', 'action', 'status']:
                    try:
                        value = getattr(step, attr)
                        if not callable(value):
                            logging.info(f"    {attr}: {value}")
                    except:
                        pass

        elif step.type == "code_interpreter_call":
            logging.info("  💻 CODE INTERPRETER CALL:")
            if hasattr(step, 'input'):
                logging.info(f"    Input: {getattr(step, 'input', 'N/A')}")
            if hasattr(step, 'output'):
                logging.info(f"    Output: {getattr(step, 'output', 'N/A')}")
            # Log any additional code interpreter metadata
            for attr in dir(step):
                if not attr.startswith('_') and attr not in ['type', 'input', 'output']:
                    try:
                        value = getattr(step, attr)
                        if not callable(value):
                            logging.info(f"    {attr}: {value}")
                    except:
                        pass
        
        else:
            # Log any other step types we haven't handled
            logging.info(f"  ❓ UNKNOWN STEP TYPE: {step.type}")
            logging.info(f"    Available attributes: {[attr for attr in dir(step) if not attr.startswith('_')]}")
            
            # Try to log common attributes that might exist
            common_attrs = ['status', 'action', 'input', 'output', 'query', 'result', 'content', 'summary']
            for attr in common_attrs:
                if hasattr(step, attr):
                    try:
                        value = getattr(step, attr)
                        if not callable(value):
                            logging.info(f"    {attr}: {value}")
                    except:
                        pass

    # --- Summary Statistics ---
    logging.info("=== INTERACTION SUMMARY ===")
    logging.info(f"Total MCP Tool Calls: {mcp_calls_count}")
    logging.info(f"Total Tool Results: {tool_results_count}")
    logging.info(f"Total Steps Processed: {len(response.output)}")
    
    # Check if we have any server information or tool discovery data
    if hasattr(response, 'servers') or hasattr(response, 'tools_discovered'):
        logging.info("=== MCP SERVER INFORMATION ===")
        if hasattr(response, 'servers'):
            logging.info(f"Servers: {response.servers}")
        if hasattr(response, 'tools_discovered'):
            logging.info(f"Tools Discovered: {response.tools_discovered}")

except Exception as e:
    logging.critical(f"An unrecoverable error occurred: {e}", exc_info=True)

logging.info("--- Script Finished ---") 