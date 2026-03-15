"""
Streaming processor module for OpenAI responses API.
Handles the actual API calls and response processing.
"""

import os
import re
import time
import logging
import warnings
from typing import Dict, Optional, Any
from datetime import datetime
from openai import OpenAI, APIError

# Import our streaming logger
from streaming_logger import StreamingLogger

# Import S3 log uploader
from s3_logs import S3LogUploader

# Suppress warnings (from test_streaming_research_v2.py)
warnings.filterwarnings("ignore", category=UserWarning, message=".*Pydantic.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*serializ.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*unexpected.*")

logger = logging.getLogger(__name__)


class StreamingProcessor:
    """Process research requests using OpenAI streaming API"""
    
    def __init__(self, api_key: str, model: str = None, use_flex: bool = True,
                 session_dir: str = None, twitter_handle: str = None, 
                 project_name: str = None, worker_id: str = None, position: int = None,
                 total: int = None, mock_mode: bool = False):
        """
        Initialize streaming processor.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (e.g., "gpt-5.1", "o3", "o4-mini")
            use_flex: Whether to use flex processing for cost savings
            session_dir: Base directory for this session
            twitter_handle: Twitter handle being researched
            project_name: Project name for consistent directory naming
            worker_id: Worker thread identifier for concurrent processing
            position: Current position in batch (for progress tracking)
            total: Total number of projects in batch (for progress tracking)
            mock_mode: If True, use mock responses for testing
        """
        self.api_key = api_key
        if not model:
            raise ValueError("Model is required for StreamingProcessor")
        self.model = model
        self.use_flex = use_flex
        self.session_dir = session_dir
        self.twitter_handle = twitter_handle
        self.project_name = project_name
        self.worker_id = worker_id
        self.position = position
        self.total = total
        self.mock_mode = mock_mode
        
        # Set timeout based on flex mode
        self.timeout = 1800.0 if use_flex else 900.0  # 30 min for flex, 15 min for instant
        
        # Initialize OpenAI client if not in mock mode
        if not mock_mode:
            self.client = OpenAI(api_key=api_key, timeout=self.timeout)
    
    def process_research(self, system_message: str, user_query: str,
                        mcp_server_url: str, max_retries: int = 3,
                        event_callback=None, file_base64: str = None) -> Optional[str]:
        """
        Execute research using streaming responses.

        Args:
            system_message: System prompt for the AI
            user_query: User's research query
            mcp_server_url: URL of the MCP server
            max_retries: Maximum number of retries for 429 errors (flex mode only)
            event_callback: Optional callback called for each streaming chunk.
                           Signature: event_callback(chunk) -> None
            file_base64: Optional base64-encoded PDF file to attach as input_file

        Returns:
            Final research output or None if failed
        """
        # Create unique session ID
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create project-specific log directory using ONLY Twitter handle
        # This matches the updated research_agent.py naming convention
        if self.session_dir and self.twitter_handle:
            # Sanitize handle for filesystem - ONLY use Twitter handle
            safe_handle = self.twitter_handle.replace('@', '')
            safe_handle = re.sub(r'[^\w]', '', safe_handle)
            
            # Use ONLY the Twitter handle as directory name
            project_dir = safe_handle
            
            log_dir = os.path.join(self.session_dir, project_dir)
        else:
            log_dir = None
        
        # Initialize streaming logger
        stream_logger = StreamingLogger(
            session_id=session_id,
            log_dir=log_dir,
            twitter_handle=self.twitter_handle,
            worker_id=self.worker_id,
            position=self.position,
            total=self.total
        )
        
        # Log initialization
        stream_logger.log_summary('🚀', f'Session started: {session_id}')
        stream_logger.log_summary('🎯', f'Researching @{self.twitter_handle or "unknown"}')
        stream_logger.log_summary('⚙️', f'Model: {self.model}')
        stream_logger.log_summary('🔌', f'MCP Server: {mcp_server_url}')
        
        # Build user message content (text + optional file attachment)
        user_content = [{"type": "input_text", "text": user_query}]
        if file_base64:
            user_content.append({
                "type": "input_file",
                "filename": "upload.pdf",
                "file_data": f"data:application/pdf;base64,{file_base64}"
            })
            stream_logger.log_summary('📎', 'PDF file attached to request')

        # Build request parameters
        request_params = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": [{"type": "input_text", "text": system_message}]},
                {"role": "user", "content": user_content}
            ],
            "tools": [
                {"type": "web_search"},
                {
                    "type": "mcp",
                    "server_label": "research_tools",
                    "server_url": mcp_server_url,
                    "require_approval": "never"
                },
            ],
            "reasoning": {"effort": "high", "summary": "detailed"},
            "stream": True  # Enable streaming
        }
        
        # Add service_tier if using flex processing
        if self.use_flex:
            request_params["service_tier"] = "flex"
            stream_logger.log_summary('💡', 'Using flex processing (cost-optimized, slower)')
        else:
            stream_logger.log_summary('⚡', 'Using instant processing (faster, higher cost)')
        
        # Handle retries
        retry_count = 0
        # For 424 errors: always allow 1 retry (2 attempts total) regardless of mode
        # For other errors: use max_retries parameter for flex mode, 1 for instant
        max_retries_424 = 2  # Always allow 1 retry for 424 errors
        max_retries_other = max_retries if self.use_flex else 1
        # Use the larger value to ensure loop doesn't exit prematurely
        max_retries_loop = max(max_retries_424, max_retries_other)

        while retry_count < max_retries_loop:
            # Assume we will not retry unless the except path signals it
            will_retry = False
            try:
                if retry_count > 0:
                    stream_logger.log_summary('🔄', f'Retry attempt {retry_count}')
                
                # Use mock or real stream
                if self.mock_mode:
                    stream = self._get_mock_stream()
                    stream_logger.log_summary('🧪', 'Using mock data for testing')
                else:
                    stream_logger.log_summary('🔄', 'Initiating API call...')
                    stream = self.client.responses.create(**request_params)
                
                stream_logger.log_summary('✅', 'Stream created successfully')
                
                # Process stream events
                for chunk in stream:
                    stream_logger.process_chunk(chunk)
                    if event_callback:
                        try:
                            event_callback(chunk)
                        except Exception as cb_err:
                            logger.debug(f"Event callback error (non-critical): {cb_err}")
                
                # Finalize and get output
                stream_logger._finalize_batches()
                final_output = stream_logger.get_final_output()
                
                # Log completion
                duration = time.time() - stream_logger.start_time
                stream_logger.log_summary('✅', f'Research completed in {duration:.1f}s')
                
                # Store the final output before closing
                # Don't close here - the finally block will handle it
                return final_output
                
            except Exception as e:
                error_str = str(e)

                # Check for 424 Failed Dependency errors (MCP server issues)
                if "Error code: 424" in error_str or (isinstance(e, APIError) and "424" in error_str):
                    retry_count += 1
                    if retry_count < max_retries_424:  # Allow 1 retry (2 attempts total)
                        wait_time = 5  # 5 second wait before retry
                        stream_logger.log_summary('⚠️', f'Got 424 error (MCP server), retrying after {wait_time}s...')
                        # Signal finally to keep logger open between attempts
                        will_retry = True
                        time.sleep(wait_time)
                        continue
                    else:
                        stream_logger.log_summary('❌', 'Retry failed for 424 error, proceeding to error handling')
                        raise  # Re-raise to trigger error counting in research_agent.py

                # Check for retryable 429 errors
                elif "429" in error_str and "Resource Unavailable" in error_str and self.use_flex:
                    retry_count += 1
                    if retry_count < max_retries_other:
                        wait_time = 30 * retry_count  # 30s, 60s, 90s
                        stream_logger.log_summary('⚠️', f'Got 429 error, waiting {wait_time}s...')
                        will_retry = True
                        time.sleep(wait_time)
                        continue
                    else:
                        stream_logger.log_summary('❌', 'Max retries reached for 429 error')
                        raise
                
                # Check for infrastructure / server errors (500, 502, 503, 504
                # and generic OpenAI APIError "An error occurred while
                # processing your request")
                elif (
                    any(code in error_str for code in ["500", "502", "503", "504"])
                    or (isinstance(e, APIError) and "error occurred while processing" in error_str.lower())
                ):
                    retry_count += 1
                    if retry_count < max_retries_other:
                        wait_time = 60 * retry_count  # 60s, 120s, 180s
                        stream_logger.log_summary('⚠️', f'Server error ({type(e).__name__}), waiting {wait_time}s...')
                        will_retry = True
                        time.sleep(wait_time)
                        continue
                    else:
                        stream_logger.log_summary('❌', 'Max retries reached for server error')
                        raise

                # Non-retryable error
                else:
                    stream_logger.log_summary('❌', f'Error: {type(e).__name__}', str(e)[:200])
                    raise
            
            finally:
                # Only close and upload if we are NOT retrying
                if not will_retry:
                    try:
                        if 'stream_logger' in locals() and stream_logger:
                            stream_logger.close()
                    except Exception as close_error:
                        logger.warning(f'Logger close failed (non-critical): {str(close_error)[:120]}')
                    
                    # Now upload logs to S3 after files are written
                    if log_dir and self.twitter_handle:
                        try:
                            logger.info('Uploading logs to S3...')
                            s3_uploader = S3LogUploader()
                            # Use asyncio to handle async upload
                            import asyncio
                            upload_success = asyncio.run(s3_uploader.upload_project_logs(log_dir, self.twitter_handle))
                            if upload_success:
                                logger.info('Logs uploaded to S3 successfully')
                            else:
                                logger.info('S3 upload skipped or failed (non-critical)')
                        except Exception as upload_error:
                            # Log but don't fail the entire process
                            logger.warning(f'S3 upload failed (non-critical): {str(upload_error)[:120]}')
                            logger.debug(f"S3 upload error details: {upload_error}")
        
        return None
    
    def _get_mock_stream(self):
        """Generate mock streaming events for testing"""
        # Import here to avoid circular dependency
        from test_streaming_mock import MockStreamResponse
        return MockStreamResponse(self.twitter_handle or "test_user")
