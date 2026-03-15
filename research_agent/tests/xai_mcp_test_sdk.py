#!/usr/bin/env python3
"""
xAI SDK Test Script with MCP Server Integration
Tests Grok models with function calling for Twitter research
Uses official xAI SDK with MCP server for tool execution
"""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import warnings
import sys
from xai_sdk.search import SearchParameters, news_source, web_source, x_source
# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)

# Clear proxy vars
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'mcp_server'))

try:
    from xai_sdk import Client
    from xai_sdk.chat import system, user, assistant, tool_result, tool as create_tool, required_tool
except ImportError:
    print("ERROR: xai-sdk not installed. Please run: pip install xai-sdk")
    sys.exit(1)

# Import tools from mcp_server
try:
    from tools import Tools
except ImportError:
    print("ERROR: Could not import tools from mcp_server. Make sure the path is correct.")
    sys.exit(1)

from dotenv import load_dotenv

# Load environment variables
load_dotenv('../../.env')  # Load from project root

# Logging setup with enhanced formatting
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'xai_sdk_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

# Create formatters
file_formatter = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Create handlers
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Log startup info
logger.info("="*60)
logger.info("xAI SDK MCP Research Test Script Starting")
logger.info("="*60)
logger.debug(f"Log file: {log_file}")
logger.debug(f"Python version: {sys.version}")
logger.debug(f"Working directory: {os.getcwd()}")

# Configuration
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")

# Log configuration
logger.debug("Configuration loaded:")
logger.debug(f"  XAI_API_KEY: {'*' * 10 + XAI_API_KEY[-4:] if XAI_API_KEY else 'NOT SET'}")

# Load system prompt from research_agent_prompt.md
def load_system_prompt():
    """Load the system prompt from xai_research_agent_prompt.md"""
    prompt_file = os.path.join(os.path.dirname(__file__), 'xai_research_agent_prompt.md')
    logger.debug(f"Looking for prompt file at: {prompt_file}")
    try:
        #return """Gather all information of the twitter/X profile handle using your built-in X search capability - following, followers, posts mentioned, associations and what this profile is"""
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.debug(f"Successfully loaded prompt file ({len(content)} chars)")
            return content
    except FileNotFoundError:
        logger.error(f"System prompt file not found: {prompt_file}")
        # Fallback to basic prompt
        return """Gather all information of the twitter/X profile handle using your built-in X search capability - following, followers, posts mentioned, associations and what this profile is"""


class XAISDKMCPResearchTester:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize xAI client using official SDK"""
        # Use provided key or let SDK pick up from env
        if api_key:
            self.client = Client(api_key=api_key)
        else:
            self.client = Client()
            
        self.system_prompt = load_system_prompt()
        
        # Initialize MCP tools locally
        self.tools = Tools()
        
        # Create tool definitions for xAI SDK
        self.tool_definitions = [
            # create_tool(
            #     name="get_twitter_profile",
            #     description="Get detailed profile information for a Twitter user by their username.",
            #     parameters={
            #         "type": "object",
            #         "properties": {
            #             "username": {
            #                 "type": "string",
            #                 "description": "The Twitter username to look up (with or without @)"
            #             }
            #         },
            #         "required": ["username"]
            #     }
            # ),
            # create_tool(
            #     name="get_twitter_following",
            #     description="Fetch profiles of accounts that the target user is following. Returns in chronological order (oldest first) to prioritize founders/early team members.",
            #     parameters={
            #         "type": "object",
            #         "properties": {
            #             "username": {
            #                 "type": "string",
            #                 "description": "The Twitter username to get followings for"
            #             },
            #             "oldest_first": {
            #                 "type": "boolean",
            #                 "description": "If True, only returns the oldest 50 followings",
            #                 "default": False
            #             }
            #         },
            #         "required": ["username"]
            #     }
            # ),
            # create_tool(
            #     name="get_twitter_tweets",
            #     description="Fetch recent tweets posted by a Twitter user.",
            #     parameters={
            #         "type": "object",
            #         "properties": {
            #             "username": {
            #                 "type": "string",
            #                 "description": "The Twitter username"
            #             },
            #             "limit": {
            #                 "type": "integer",
            #                 "description": "Number of tweets to fetch (default 20, max 20)",
            #                 "default": 20
            #             }
            #         },
            #         "required": ["username"]
            #     }
            # ),
            create_tool(
                name="scrape_website",
                description="Scrape a single URL and return its text content in markdown format.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to scrape"
                        }
                    },
                    "required": ["url"]
                }
            )
        ]
        
        # Create function mapping for tool execution
        self.tools_map = {
            # "get_twitter_profile": self.tools.get_twitter_profile,
            # "get_twitter_following": self.tools.get_twitter_following,
            # "get_twitter_tweets": self.tools.get_twitter_tweets,
             "scrape_website": self.tools.scrape_website
        }
        
        logger.info("Initialized xAI SDK client with function calling support")
        logger.info(f"Available tools: {list(self.tools_map.keys())}")
        logger.info(f"System prompt loaded: {len(self.system_prompt)} chars")
    
    def research_twitter_profile(self, username: str) -> Dict[str, Any]:
        """Research a Twitter profile using xAI SDK with streaming and function calling"""
        logger.info(f"Starting research for Twitter profile: @{username}")
        logger.info("Using streaming with function calling to execute tools locally")
        
        try:
            logger.info("Creating chat session with function calling...")
            start_time = datetime.now()
            
            # Create chat object with tools
            chat = self.client.chat.create(
                model="grok-4-0709",  # Using latest model
                search_parameters=SearchParameters(mode="on",sources=[
            web_source(),
            x_source(),
            news_source(),
        ],),
                 tools=self.tool_definitions,
                temperature=0.7,
                max_tokens=80000  # Increased for comprehensive report
            )
            
            # Add system message and user query
            chat.append(system(self.system_prompt))
            # Add explicit instruction to use the required Twitter tools
            chat.append(user(f"""Research @{username}. 

Research @{username}."""))
            
            logger.info("Starting streaming request to xAI...")
            
            # Keep track of conversation history
            iteration = 0
            max_iterations = 40  # Safety limit for tool calling loops
            final_content_parts = []
            tool_call_count = 0
            tools_called = set()  # Track which tools have been called
            
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"\n=== ITERATION {iteration} ===")
                logger.info("Streaming response from model...")
                
                # Variables for this iteration
                current_content = []
                pending_tool_calls = []
                chunk_count = 0
                has_tool_calls = False
                streamed_response = None
                
                # Stream the response
                logger.debug(f"Beginning to stream chunks...")
                for response, chunk in chat.stream():
                    chunk_count += 1
                    streamed_response = response  # Keep the response for later use
                    
                    # Simple progress indicator every 10 chunks
                    if chunk_count % 10 == 0:
                        logger.debug(f"Streaming progress: {chunk_count} chunks received...")
                    
                    # Only log meaningful updates, not every chunk
                    # Skip logging repetitive "Thinking..." chunks
                    if hasattr(response, 'reasoning_content') and response.reasoning_content:
                        reasoning = response.reasoning_content
                        # Only log if it's not just repeated "Thinking..."
                        if reasoning and not reasoning.strip().replace('Thinking... ', '').replace('Thinking...', ''):
                            # Skip logging, this is just spam
                            pass
                        else:
                            # This might have actual reasoning content
                            logger.debug(f"[Chunk {chunk_count}] Reasoning: {reasoning[:100]}...")
                    
                    # Log citations if available (for web search)
                    if hasattr(response, 'citations') and response.citations:
                        logger.info(f"\n[Chunk {chunk_count}] Web search citations:")
                        for i, citation in enumerate(response.citations):
                            logger.info(f"  [{i+1}] {citation}")
                    
                    # According to docs, function calls come in a single chunk
                    if hasattr(response, 'tool_calls') and response.tool_calls:
                        has_tool_calls = True
                        pending_tool_calls = response.tool_calls
                        logger.info(f"\n[Chunk {chunk_count}] Received {len(pending_tool_calls)} tool calls in single chunk")
                        
                        # Log tool calls
                        for tc in pending_tool_calls:
                            logger.info(f"  - Tool: {tc.function.name}")
                            logger.debug(f"    Args: {tc.function.arguments}")
                    
                    # Regular content chunks
                    if hasattr(chunk, 'content') and chunk.content:
                        content = chunk.content
                        current_content.append(content)
                        
                        # Log content chunks
                        if len(content.strip()) > 0:
                            logger.debug(f"[Chunk {chunk_count}] Content: {content[:100]}...")
                
                logger.info(f"Streaming complete. Received {chunk_count} chunks")
                
                # Process tool calls if any
                if has_tool_calls and pending_tool_calls:
                    logger.info(f"\nProcessing {len(pending_tool_calls)} tool calls...")
                    tool_call_count += len(pending_tool_calls)
                    
                    # Append the streamed response which contains the tool calls
                    if streamed_response:
                        chat.append(streamed_response)
                    
                    # Execute each tool call
                    for i, tool_call in enumerate(pending_tool_calls):
                        logger.info(f"\n--- Executing Tool Call {i+1}/{len(pending_tool_calls)} ---")
                        function_name = tool_call.function.name
                        logger.info(f"Tool: {function_name}")
                        tools_called.add(function_name)  # Track tool usage
                        
                        try:
                            # Parse arguments
                            function_args = json.loads(tool_call.function.arguments)
                            logger.info(f"Arguments: {json.dumps(function_args, indent=2)}")
                            
                            # Execute the tool
                            logger.info(f"Executing {function_name}...")
                            result = self.tools_map[function_name](**function_args)
                            
                            # Log result summary
                            result_str = json.dumps(result, indent=2)
                            logger.info(f"Result preview: {result_str[:500]}...")
                            if len(result_str) > 500:
                                logger.debug(f"Full result ({len(result_str)} chars): {result_str}")
                            
                            # Add tool result to chat
                            # tool_result() only takes a string in xAI SDK
                            chat.append(tool_result(json.dumps(result)))
                            
                            logger.info(f"Added tool result to conversation")
                            
                        except Exception as e:
                            logger.error(f"Error executing tool {function_name}: {e}")
                            logger.exception("Tool execution traceback:")
                            
                            # Add error result
                            error_result = {"error": f"Tool execution failed: {str(e)}"}
                            chat.append(tool_result(json.dumps(error_result)))
                    
                    logger.info("All tool calls processed, continuing to next iteration...")
                    
                else:
                    # No tool calls, this is final content
                    logger.info("No tool calls in response - this is the final answer")
                    final_content = ''.join(current_content)
                    if final_content:
                        final_content_parts.append(final_content)
                    break
            
            # Log timing and summary
            response_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"\n=== STREAMING WITH FUNCTION CALLING COMPLETED ===")
            logger.info(f"Total iterations: {iteration}")
            logger.info(f"Total tool calls: {tool_call_count}")
            logger.info(f"Tools used: {sorted(tools_called)}")
            logger.info(f"Total time: {response_time:.2f} seconds")
            
            # Log final usage metrics if available
            if streamed_response and hasattr(streamed_response, 'usage') and streamed_response.usage:
                final_usage = streamed_response.usage
                logger.info(f"\n=== FINAL USAGE METRICS ===")
                logger.info(f"Total tokens: {final_usage.total_tokens}")
                logger.info(f"Prompt tokens: {final_usage.prompt_tokens}")
                logger.info(f"Completion tokens: {final_usage.completion_tokens}")
                logger.info(f"Reasoning tokens: {final_usage.reasoning_tokens}")
                logger.info(f"Cached prompt tokens: {final_usage.cached_prompt_text_tokens}")
                logger.info(f"Sources used: {final_usage.num_sources_used}")
                
                # Calculate costs if reasoning tokens are present
                if final_usage.reasoning_tokens > 0:
                    logger.info(f"\n=== TOKEN BREAKDOWN ===")
                    logger.info(f"Reasoning tokens: {final_usage.reasoning_tokens} ({final_usage.reasoning_tokens / final_usage.total_tokens * 100:.1f}% of total)")
                    logger.info(f"Non-reasoning completion: {final_usage.completion_tokens - final_usage.reasoning_tokens}")
            
            # Log final reasoning content if available and meaningful
            if streamed_response and hasattr(streamed_response, 'reasoning_content') and streamed_response.reasoning_content:
                reasoning_content = streamed_response.reasoning_content
                # Check if it's just repeated "Thinking..."
                cleaned_reasoning = reasoning_content.strip().replace('Thinking... ', '').replace('Thinking...', '')
                if cleaned_reasoning:  # Has actual content beyond "Thinking..."
                    logger.info(f"\n=== FINAL REASONING TRACE ===")
                    logger.info(f"Reasoning length: {len(reasoning_content)} characters")
                    logger.debug(f"Full reasoning trace:\n{reasoning_content}")
                else:
                    logger.debug(f"Reasoning was just 'Thinking...' repeated ({len(reasoning_content)} chars)")
            
            # Log final citations if available
            if streamed_response and hasattr(streamed_response, 'citations') and streamed_response.citations:
                logger.info(f"\n=== WEB SEARCH CITATIONS ===")
                logger.info(f"Total citations: {len(streamed_response.citations)}")
                for i, citation in enumerate(streamed_response.citations):
                    logger.info(f"  [{i+1}] {citation}")
            
            
            # Combine all final content
            final_content = ''.join(final_content_parts)
            
            if final_content:
                logger.info(f"Successfully generated research report ({len(final_content)} chars)")
                
                # Save response with all metadata
                usage_data = None
                reasoning_content = None
                citations = []
                
                if streamed_response:
                    if hasattr(streamed_response, 'usage') and streamed_response.usage:
                        usage_data = {
                            'total_tokens': streamed_response.usage.total_tokens,
                            'prompt_tokens': streamed_response.usage.prompt_tokens,
                            'completion_tokens': streamed_response.usage.completion_tokens,
                            'reasoning_tokens': streamed_response.usage.reasoning_tokens,
                            'cached_prompt_text_tokens': streamed_response.usage.cached_prompt_text_tokens,
                            'num_sources_used': streamed_response.usage.num_sources_used
                        }
                    
                    if hasattr(streamed_response, 'reasoning_content'):
                        reasoning_content = streamed_response.reasoning_content
                    
                    if hasattr(streamed_response, 'citations'):
                        citations = list(streamed_response.citations)
                
                self._save_function_calling_response(
                    username, final_content, iteration, response_time, tool_call_count,
                    usage_data, reasoning_content, citations, tools_called
                )
                
                # Return comprehensive result
                return {
                    'report': final_content,
                    'usage': usage_data,
                    'tool_count': tool_call_count,
                    'tools_used': tools_called,
                    'iterations': iteration,
                    'response_time': response_time,
                    'reasoning_content': reasoning_content,
                    'citations': citations
                }
            else:
                logger.error("No final content generated")
                return {
                    'report': "Error: No final content generated",
                    'error': True
                }
                
        except Exception as e:
            logger.error(f"Error during research: {type(e).__name__}: {str(e)}")
            logger.exception("Full traceback:")
            return {
                'report': f"Error during research: {str(e)}",
                'error': True,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
    
    def _save_function_calling_response(self, username: str, content: str, iterations: int, response_time: float, 
                                       tool_call_count: int = 0, usage_data: Optional[Dict] = None,
                                       reasoning_content: Optional[str] = None, citations: Optional[List[str]] = None,
                                       tools_called: Optional[set] = None):
        """Save function calling response with comprehensive metadata"""
        try:
            debug_dir = 'debug'
            os.makedirs(debug_dir, exist_ok=True)
            
            # Create detailed response record
            response_data = {
                'timestamp': datetime.now().isoformat(),
                'username': username,
                'model': 'grok-4-0709',
                'mode': 'streaming_with_function_calling',
                'iterations': iterations,
                'tool_call_count': tool_call_count,
                'tools_called': sorted(list(tools_called)) if tools_called else [],
                'response_time_seconds': response_time,
                'content_length': len(content),
                'content_preview': content[:5000] + '...' if len(content) > 5000 else content,
                'usage': usage_data,
                'reasoning_content_length': len(reasoning_content) if reasoning_content else 0,
                'reasoning_content_preview': reasoning_content[:1000] + '...' if reasoning_content and len(reasoning_content) > 1000 else reasoning_content,
                'citations': citations if citations else [],
                'citations_count': len(citations) if citations else 0
            }
            
            # Save to JSON file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            debug_file = os.path.join(debug_dir, f"function_calling_{username}_{timestamp}.json")
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved function calling response to: {debug_file}")
            
            # Save full reasoning trace if available and meaningful
            if reasoning_content:
                # Check if it's just repeated "Thinking..."
                cleaned_reasoning = reasoning_content.strip().replace('Thinking... ', '').replace('Thinking...', '')
                if cleaned_reasoning:  # Has actual content
                    reasoning_file = os.path.join(debug_dir, f"reasoning_trace_{username}_{timestamp}.md")
                    with open(reasoning_file, 'w', encoding='utf-8') as f:
                        f.write(f"# Reasoning Trace for @{username}\n\n")
                        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"Model: grok-4-0709\n")
                        f.write(f"Reasoning tokens: {usage_data.get('reasoning_tokens', 'N/A') if usage_data else 'N/A'}\n\n")
                        f.write("---\n\n")
                        f.write(reasoning_content)
                    logger.debug(f"Saved reasoning trace to: {reasoning_file}")
            
        except Exception as e:
            logger.error(f"Failed to save function calling response: {e}")
    
    
    
    def save_report(self, username: str, report: str, usage_data: Optional[Dict] = None,
                    tool_count: int = 0, tools_used: Optional[set] = None):
        """Save the research report to a markdown file with metadata"""
        reports_dir = 'reports'
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = os.path.join(reports_dir, f"xai_sdk_research_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Twitter Research Report for @{username}\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Model: xAI Grok-4-0709\n")
            f.write(f"Mode: Function Calling with Streaming\n")
            f.write(f"SDK: xAI SDK (official)\n")
            
            # Add usage metrics if available
            if usage_data:
                f.write(f"\n## Token Usage\n")
                f.write(f"- Total tokens: {usage_data.get('total_tokens', 'N/A')}\n")
                f.write(f"- Prompt tokens: {usage_data.get('prompt_tokens', 'N/A')}\n")
                f.write(f"- Completion tokens: {usage_data.get('completion_tokens', 'N/A')}\n")
                f.write(f"- Reasoning tokens: {usage_data.get('reasoning_tokens', 'N/A')}\n")
                f.write(f"- Sources used: {usage_data.get('num_sources_used', 0)}\n")
            
            # Add tool usage info
            if tool_count > 0 or tools_used:
                f.write(f"\n## Tool Usage\n")
                f.write(f"- Total tool calls: {tool_count}\n")
                if tools_used:
                    f.write(f"- Tools used: {', '.join(sorted(tools_used))}\n")
            
            f.write("\n---\n\n")
            f.write(report)
        logger.info(f"Report saved to: {filename}")
        return filename




def main():
    """Main test function"""
    # Validate configuration
    logger.debug("Validating configuration...")
    if not XAI_API_KEY:
        logger.error("Missing XAI_API_KEY in environment variables")
        logger.info("Please add XAI_API_KEY to your .env file")
        logger.info("Get your API key from: https://console.x.ai")
        return
    else:
        logger.debug("XAI_API_KEY is configured")
    
    # Check if API keys for tools are configured
    logger.info("Checking tool API keys...")
    tools = Tools()
    if not tools.rapid_api_key:
        logger.warning("RAPID_API_KEY not configured - Twitter tools will not work")
    else:
        logger.info("âœ?RAPID_API_KEY configured")
    
    if not tools.firecrawl_api_key:
        logger.warning("FIRECRAWL_API_KEY not configured - Web scraping tools will not work")
    else:
        logger.info("âœ?FIRECRAWL_API_KEY configured")
    
    # Get Twitter username to research
    if len(sys.argv) > 1:
        username = sys.argv[1].strip().replace('@', '')
    else:
        username = input("Enter Twitter username to research (without @): ").strip()
    
    if not username:
        logger.error("No username provided")
        return
    
    # Initialize tester
    logger.debug(f"Initializing research tester for username: {username}")
    tester = XAISDKMCPResearchTester(XAI_API_KEY)
    
    # Perform research
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting xAI SDK research for @{username}")
    logger.info(f"Using function calling with local tool execution")
    logger.info(f"Model: grok-4-0709 with streaming support")
    logger.info(f"Tool choice: required (model must use tools)")
    logger.info(f"{'='*60}\n")
    
    start_time = datetime.now()
    logger.debug(f"Research started at: {start_time}")
    
    # Store the report and metadata
    result = tester.research_twitter_profile(username)
    duration = (datetime.now() - start_time).total_seconds()
    logger.debug(f"Research completed in {duration:.2f} seconds")
    
    # Extract report and metadata
    report = result.get('report', '')
    usage_data = result.get('usage')
    tool_count = result.get('tool_count', 0)
    tools_used = result.get('tools_used', set())
    
    # Save report
    logger.debug(f"Report length: {len(report) if report else 0} chars")
    if report and not result.get('error', False):
        logger.debug("Saving successful report...")
        filename = tester.save_report(username, report, usage_data, tool_count, tools_used)
        logger.info(f"\n{'='*60}")
        logger.info(f"Research completed in {duration:.2f} seconds")
        logger.info(f"Report saved to: {filename}")
        logger.info(f"Log file: {log_file}")
        
        # Log final metrics
        if usage_data:
            logger.info(f"\n=== FINAL METRICS ===")
            logger.info(f"Total tokens: {usage_data.get('total_tokens', 'N/A')}")
            logger.info(f"Reasoning tokens: {usage_data.get('reasoning_tokens', 'N/A')}")
            if usage_data.get('reasoning_tokens', 0) > 0 and usage_data.get('total_tokens', 0) > 0:
                reasoning_pct = usage_data['reasoning_tokens'] / usage_data['total_tokens'] * 100
                logger.info(f"Reasoning percentage: {reasoning_pct:.1f}%")
            logger.info(f"Web sources used: {usage_data.get('num_sources_used', 0)}")
        
        if tool_count > 0:
            logger.info(f"\nTool calls made: {tool_count}")
            if tools_used:
                logger.info(f"Tools used: {', '.join(sorted(tools_used))}")
        
        logger.info(f"{'='*60}")
        
        # Display report preview
        print("\n" + "="*60)
        print("RESEARCH REPORT PREVIEW")
        print("="*60)
        print(report[:2000] + "..." if len(report) > 2000 else report)
        print("="*60)
        print(f"\nFull report saved to: {filename}")
        
        # Display reasoning preview if available and meaningful
        if result.get('reasoning_content'):
            reasoning = result['reasoning_content']
            # Check if it's just repeated "Thinking..."
            cleaned_reasoning = reasoning.strip().replace('Thinking... ', '').replace('Thinking...', '')
            if cleaned_reasoning:  # Has actual content
                print("\n" + "="*60)
                print("REASONING TRACE PREVIEW")
                print("="*60)
                print(reasoning[:1000] + "..." if len(reasoning) > 1000 else reasoning)
                print("="*60)
        
        # Display citations if available
        if result.get('citations'):
            print("\n" + "="*60)
            print("WEB SEARCH CITATIONS")
            print("="*60)
            for i, citation in enumerate(result['citations'][:10]):  # Show first 10
                print(f"[{i+1}] {citation}")
            if len(result['citations']) > 10:
                print(f"... and {len(result['citations']) - 10} more citations")
            print("="*60)
    else:
        logger.error(f"Research failed: {report}")


if __name__ == "__main__":
    main()