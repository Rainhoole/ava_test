"""
Streaming logger module - closely based on test_streaming_research_v2.py
Minimal modifications for concurrent support and project organization.
"""

import os
import json
import logging
import time
from typing import Dict, Optional, Any, List
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

# Event categories for filtering (from test_streaming_research_v2.py)
IMPORTANT_EVENTS = {
    'lifecycle': [
        'response.created', 
        'response.in_progress', 
        'response.completed'
    ],
    'tools': [
        'response.mcp_call',
        'response.mcp_list_tools',
        'response.web_search_call'
    ],
    'content': [
        'response.output_text.delta',
        'response.reasoning_summary_text.delta'
    ],
    'milestones': [
        'response.output_item.added',
        'response.output_item.done',
        'response.content_part.added',
        'response.content_part.done',
        'response.reasoning_summary_part.added',
        'response.reasoning_summary_part.done'
    ]
}

# Events to skip entirely
SKIP_EVENTS = {
    'response.mcp_call_arguments.delta',  # Too granular
    'response.mcp_call_arguments.done',
    'response.web_search_call.searching',  # Intermediate state
}


class StreamingLogger:
    """Enhanced logging system for streaming responses - from test_streaming_research_v2.py"""
    
    def __init__(self, session_id: str, log_dir: str = None, twitter_handle: str = None, 
                 worker_id: str = None, position: int = None, total: int = None):
        """
        Initialize streaming logger.
        Modified from test_streaming_research_v2.py to support project organization.
        
        Args:
            session_id: Unique session identifier  
            log_dir: Directory for logs (e.g., logs/projects_YYYYMMDD_HHMMSS/handle_project)
            twitter_handle: Twitter handle for console output prefix
            worker_id: Worker thread identifier for concurrent processing
            position: Current position in batch (for progress tracking)
            total: Total number of projects in batch (for progress tracking)
        """
        self.session_id = session_id
        self.twitter_handle = twitter_handle
        self.worker_id = worker_id
        self.position = position
        self.total = total
        self.start_time = time.time()
        
        # Create session directory - modified to use provided log_dir
        if log_dir:
            self.log_dir = log_dir
        else:
            self.log_dir = f'logs/streaming_session_{session_id}'
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Initialize log files (same as test_streaming_research_v2.py)
        # Files created:
        # - 01_summary.log: Timeline with key events and progress
        # - 02_reasoning.md: Full reasoning text
        # - 03_tools.jsonl: Tool calls with full details
        # - 04_metrics.json: Performance metrics (written at end)
        # - final_output.md: Complete final output (written at end)
        # - raw_events.jsonl: Complete raw stream for debugging
        self.files = {
            # Use append mode for summary since research logger might also write to it
            'summary': open(os.path.join(self.log_dir, '01_summary.log'), 'a', encoding='utf-8'),
            'reasoning': open(os.path.join(self.log_dir, '02_reasoning.md'), 'w', encoding='utf-8'),
            'tools': open(os.path.join(self.log_dir, '03_tools.jsonl'), 'w', encoding='utf-8'),
            'metrics': None,  # Will write at the end
            'raw': open(os.path.join(self.log_dir, 'raw_events.jsonl'), 'w', encoding='utf-8')
        }
        
        # Accumulators (identical to test_streaming_research_v2.py)
        self.reasoning_parts = []
        self.output_parts = []
        self.tool_calls = []
        self.web_searches = []
        self.metrics = {
            'start_time': datetime.now().isoformat(),
            'chunks_total': 0,
            'chunks_by_type': defaultdict(int),
            'tools_called': [],
            'web_searches': [],
            'reasoning_parts': 0,
            'output_parts': 0,
            'tokens': {
                'reasoning': 0,
                'output': 0,
                'input': 0,
                'cached_input': 0,
                'total': 0
            },
            'mcp_tool_details': []
        }
        
        # State tracking (identical to test_streaming_research_v2.py)
        self.current_reasoning_batch = []
        self.current_output_batch = []
        self.last_progress_time = time.time()
        self.current_mcp_call = None
        
    def get_elapsed(self) -> str:
        """Get elapsed time in MM:SS.mmm format"""
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        return f"{minutes:02d}:{seconds:06.3f}"
    
    def log_summary(self, icon: str, message: str, details: str = None):
        """Log to summary file with timestamp and icon - modified for worker/handle prefix"""
        timestamp = self.get_elapsed()
        
        # Build prefix for concurrent processing with progress tracking
        prefix = ""
        if self.worker_id and self.worker_id != "MainThread":
            prefix = f"[{self.worker_id}] "
        # Add progress tracking if available
        if self.position is not None and self.total is not None:
            prefix += f"[{self.position}/{self.total}] "
        if self.twitter_handle:
            prefix += f"[@{self.twitter_handle}] "
        
        line = f"[{timestamp}] {icon} {message}"
        if details:
            line += f"\n            {details}"

        # Log to console first so we never lose diagnostics
        console_msg = f"[{timestamp}] {prefix}{icon} {message}"
        if details:
            console_msg += f" | {details}"
        logger.info(console_msg)

        # Best-effort write to summary file; guard against closed/None handles
        try:
            summary_f = self.files.get('summary')
            if summary_f and not summary_f.closed:
                summary_f.write(line + '\n')
                summary_f.flush()
            else:
                logger.debug('Summary file handle is unavailable or closed; skipping file write')
        except Exception as e:
            logger.warning(f'Failed to write summary log (non-critical): {str(e)[:120]}')
    
    def process_chunk(self, chunk: Any):
        """Process a single chunk from the stream - identical to test_streaming_research_v2.py"""
        self.metrics['chunks_total'] += 1
        
        # Always log raw event
        try:
            if hasattr(chunk, 'model_dump_json'):
                raw_data = json.loads(chunk.model_dump_json())
            elif hasattr(chunk, 'model_dump'):
                raw_data = chunk.model_dump()
            else:
                raw_data = {'type': str(type(chunk)), 'data': str(chunk)[:1000]}
            
            self.files['raw'].write(json.dumps({
                'timestamp': time.time(),
                'elapsed': time.time() - self.start_time,
                'data': raw_data
            }) + '\n')
            self.files['raw'].flush()
        except Exception as e:
            self.files['raw'].write(json.dumps({
                'timestamp': time.time(),
                'error': str(e)
            }) + '\n')
        
        # Process by type (identical logic to test_streaming_research_v2.py)
        if hasattr(chunk, 'type'):
            event_type = chunk.type
            self.metrics['chunks_by_type'][event_type] += 1
            
            # Skip noisy events
            if event_type in SKIP_EVENTS:
                return
            
            # Lifecycle events
            if event_type == 'response.created':
                self.log_summary('✅', 'Stream initialized')
            elif event_type == 'response.in_progress':
                self.log_summary('📋', 'Response processing started')
            elif event_type == 'response.completed':
                self._finalize_batches()
                duration = time.time() - self.start_time
                self.log_summary('✅', f'Response completed in {duration:.1f}s')
                
                # Extract usage information from completed response
                if hasattr(chunk, 'response'):
                    response = chunk.response
                    if hasattr(response, 'usage'):
                        usage = response.usage
                        # Update token metrics
                        self.metrics['tokens']['input'] = getattr(usage, 'input_tokens', 0)
                        self.metrics['tokens']['output'] = getattr(usage, 'output_tokens', 0)
                        self.metrics['tokens']['total'] = getattr(usage, 'total_tokens', 0)
                        
                        # Get cached tokens from input_tokens_details
                        if hasattr(usage, 'input_tokens_details'):
                            details = usage.input_tokens_details
                            self.metrics['tokens']['cached_input'] = getattr(details, 'cached_tokens', 0)
                        else:
                            self.metrics['tokens']['cached_input'] = 0
                        
                        # Log token usage
                        self.log_summary('💰', 'Token Usage:', 
                                       f"Input: {self.metrics['tokens']['input']:,} "
                                       f"(Cached: {self.metrics['tokens']['cached_input']:,}), "
                                       f"Output: {self.metrics['tokens']['output']:,}, "
                                       f"Total: {self.metrics['tokens']['total']:,}")
            
            # Tool events
            elif event_type == 'response.mcp_list_tools.completed':
                self.log_summary('🔧', 'MCP Tools Listed')
            
            # Skip output_item.added - wait for complete data in done
            elif event_type == 'response.output_item.added':
                pass
            
            # Capture complete MCP tool calls from output_item.done events
            elif event_type == 'response.output_item.done':
                if hasattr(chunk, 'item') and chunk.item:
                    item = chunk.item
                    if hasattr(item, 'type') and item.type == 'mcp_call':
                        tool_name = getattr(item, 'name', 'unknown')
                        
                        # Convert entire item to dict for logging
                        try:
                            if hasattr(item, 'model_dump'):
                                item_dict = item.model_dump()
                            elif hasattr(item, '__dict__'):
                                item_dict = {k: v for k, v in item.__dict__.items() if not k.startswith('_')}
                            else:
                                item_dict = {'name': tool_name, 'raw': str(item)}
                        except:
                            item_dict = {'name': tool_name, 'error': 'Could not serialize'}
                        
                        # Add timestamp
                        item_dict['timestamp'] = self.get_elapsed()
                        
                        # Log everything to tools file
                        self.metrics['tools_called'].append(tool_name)
                        self.tool_calls.append(item_dict)
                        self.files['tools'].write(json.dumps(item_dict) + '\n')
                        self.files['tools'].flush()
                        
                        # Log to summary with arguments preview
                        args_preview = ''
                        if 'arguments' in item_dict and item_dict['arguments']:
                            try:
                                args = json.loads(item_dict['arguments']) if isinstance(item_dict['arguments'], str) else item_dict['arguments']
                                if 'username' in args:
                                    args_preview = f"@{args['username']}"
                                elif 'url' in args:
                                    args_preview = args['url'][:50] + '...' if len(args['url']) > 50 else args['url']
                            except:
                                args_preview = str(item_dict['arguments'])[:50]
                        
                        if args_preview:
                            self.log_summary('📊', f'MCP: {tool_name}', args_preview)
                        else:
                            self.log_summary('📊', f'MCP: {tool_name}')
            
            elif event_type == 'response.mcp_call.in_progress':
                # Track for argument matching if needed
                if hasattr(chunk, 'item_id'):
                    self.current_mcp_call = {
                        'item_id': chunk.item_id,
                        'timestamp': self.get_elapsed()
                    }
            elif event_type == 'response.mcp_call_arguments.done':
                # Skip - we capture everything from output_item.added/done
                pass
            elif event_type == 'response.web_search_call.in_progress':
                if hasattr(chunk, 'query'):
                    query = chunk.query
                    self.metrics['web_searches'].append(query)
                    self.web_searches.append({
                        'timestamp': self.get_elapsed(),
                        'query': query
                    })
                    self.log_summary('🔍', f'Web Search: "{query[:50]}..."' if len(query) > 50 else f'Web Search: "{query}"')
                    self.files['tools'].write(json.dumps(self.web_searches[-1]) + '\n')
                    self.files['tools'].flush()
            
            # Content events (batch these)
            elif event_type == 'response.reasoning_summary_text.delta':
                if hasattr(chunk, 'text'):
                    text = chunk.text
                elif hasattr(chunk, 'delta'):
                    text = chunk.delta
                else:
                    text = ''
                
                if text:
                    self.current_reasoning_batch.append(text)
                    self.reasoning_parts.append(text)
                    self.metrics['tokens']['reasoning'] += len(text)
                    
                    # Log batch every 10 parts or 3 seconds
                    if len(self.current_reasoning_batch) >= 10 or (time.time() - self.last_progress_time) > 3:
                        self._log_reasoning_batch()
                        
            elif event_type == 'response.output_text.delta':
                if hasattr(chunk, 'text'):
                    text = chunk.text
                elif hasattr(chunk, 'delta'):
                    text = chunk.delta
                else:
                    text = ''
                
                if text:
                    self.current_output_batch.append(text)
                    self.output_parts.append(text)
                    self.metrics['tokens']['output'] += len(text)
                    
                    # Log batch every 10 parts or 3 seconds
                    if len(self.current_output_batch) >= 10 or (time.time() - self.last_progress_time) > 3:
                        self._log_output_batch()
            
            # Milestone events
            elif event_type == 'response.reasoning_summary_part.added':
                self.metrics['reasoning_parts'] += 1
                if self.metrics['reasoning_parts'] == 1:
                    self.log_summary('💭', 'Reasoning Started')
            elif event_type == 'response.reasoning_summary_part.done':
                # Flush any remaining reasoning
                if self.current_reasoning_batch:
                    self._log_reasoning_batch()
            elif event_type == 'response.content_part.added':
                self.metrics['output_parts'] += 1
                if self.metrics['output_parts'] == 1:
                    self.log_summary('📝', 'Output Generation Started')
            elif event_type == 'response.content_part.done':
                # Flush any remaining output
                if self.current_output_batch:
                    self._log_output_batch()
    
    def _log_reasoning_batch(self):
        """Log accumulated reasoning text - identical to test_streaming_research_v2.py"""
        if not self.current_reasoning_batch:
            return
        
        batch_text = ''.join(self.current_reasoning_batch)
        char_count = len(batch_text)
        
        # Write to reasoning file
        self.files['reasoning'].write(batch_text)
        self.files['reasoning'].flush()
        
        # Log summary
        preview = batch_text[:100].replace('\n', ' ')
        if len(preview) > 50:
            preview = preview[:50] + '...'
        self.log_summary('💭', f'Reasoning: +{char_count} chars', preview)
        
        self.current_reasoning_batch = []
        self.last_progress_time = time.time()
    
    def _log_output_batch(self):
        """Log accumulated output text - identical to test_streaming_research_v2.py"""
        if not self.current_output_batch:
            return
        
        batch_text = ''.join(self.current_output_batch)
        char_count = len(batch_text)
        
        # Try to extract section headers
        section_match = None
        if '=== SECTION:' in batch_text:
            lines = batch_text.split('\n')
            for line in lines:
                if '=== SECTION:' in line:
                    section_match = line.replace('=== SECTION:', '').replace('===', '').strip()
                    break
        
        # Log summary
        if section_match:
            self.log_summary('📝', f'Section: {section_match} (+{char_count} chars)')
        else:
            preview = batch_text[:100].replace('\n', ' ')
            if len(preview) > 50:
                preview = preview[:50] + '...'
            self.log_summary('📝', f'Output: +{char_count} chars', preview)
        
        self.current_output_batch = []
        self.last_progress_time = time.time()
    
    def _finalize_batches(self):
        """Flush any remaining batches"""
        if self.current_reasoning_batch:
            self._log_reasoning_batch()
        if self.current_output_batch:
            self._log_output_batch()
    
    def get_final_output(self) -> str:
        """Get the final accumulated output - NEW method for integration"""
        return ''.join(self.output_parts)
    
    def close(self):
        """Close all files and write final metrics - identical to test_streaming_research_v2.py"""
        # Check if already closed
        if not hasattr(self, 'files') or self.files.get('summary') is None:
            return  # Already closed
            
        # Calculate final character counts
        total_reasoning_chars = len(''.join(self.reasoning_parts))
        total_output_chars = len(''.join(self.output_parts))
        
        # Save the final accumulated output as a markdown file
        if self.output_parts:
            final_output = ''.join(self.output_parts)
            final_output_file = os.path.join(self.log_dir, 'final_output.md')
            with open(final_output_file, 'w', encoding='utf-8') as f:
                f.write(final_output)
            
            # Modified console output for concurrent support
            prefix = ""
            if self.worker_id and self.worker_id != "MainThread":
                prefix = f"[{self.worker_id}] "
            if self.twitter_handle:
                prefix += f"[@{self.twitter_handle}] "
            logger.info(f"{prefix}💾 Final output saved to: {final_output_file}")
        
        # Write final metrics
        self.metrics['end_time'] = datetime.now().isoformat()
        self.metrics['duration_seconds'] = time.time() - self.start_time
        self.metrics['total_reasoning_chars'] = total_reasoning_chars
        self.metrics['total_output_chars'] = total_output_chars
        
        with open(os.path.join(self.log_dir, '04_metrics.json'), 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        # Write final summary (check if file is still open)
        if self.files.get('summary') and not self.files['summary'].closed:
            self.files['summary'].write('\n' + '=' * 60 + '\n')
            self.files['summary'].write('=== SESSION SUMMARY ===\n')
            self.files['summary'].write(f'Duration: {self.metrics["duration_seconds"]:.1f}s\n')
            self.files['summary'].write(f'Total Chunks: {self.metrics["chunks_total"]}\n')
            self.files['summary'].write(f'Reasoning: {total_reasoning_chars:,} chars\n')
            self.files['summary'].write(f'Output: {total_output_chars:,} chars\n')
            self.files['summary'].write(f'Tools Used: {len(self.metrics["tools_called"])}\n')
            if self.metrics["tools_called"]:
                for tool in set(self.metrics["tools_called"]):
                    count = self.metrics["tools_called"].count(tool)
                    self.files['summary'].write(f'  • {tool}: {count}x\n')
            self.files['summary'].write(f'Web Searches: {len(self.metrics["web_searches"])}\n')
        
        # Write token usage summary
        tokens = self.metrics['tokens']
        if tokens['total'] > 0 and self.files.get('summary') and not self.files['summary'].closed:
            self.files['summary'].write('\n=== TOKEN USAGE ===\n')
            self.files['summary'].write(f'Input Tokens: {tokens["input"]:,}\n')
            self.files['summary'].write(f'Cached Input: {tokens["cached_input"]:,}\n')
            self.files['summary'].write(f'Output Tokens: {tokens["output"]:,}\n')
            self.files['summary'].write(f'Total Tokens: {tokens["total"]:,}\n')
            
            # Calculate costs using GPT-5 pricing
            # GPT-5 rates: Input $1.25/1M, Cached $0.125/1M, Output $10/1M
            input_cost = (tokens["input"] - tokens["cached_input"]) * 1.25 / 1_000_000  # $1.25 per 1M tokens
            cached_cost = tokens["cached_input"] * 0.125 / 1_000_000  # $0.125 per 1M tokens
            output_cost = tokens["output"] * 10.0 / 1_000_000  # $10 per 1M tokens
            total_cost = input_cost + cached_cost + output_cost
            
            self.files['summary'].write(f'\nEstimated Cost (GPT-5 rates):\n')
            self.files['summary'].write(f'  Input: ${input_cost:.4f}\n')
            self.files['summary'].write(f'  Cached: ${cached_cost:.4f}\n')
            self.files['summary'].write(f'  Output: ${output_cost:.4f}\n')
            self.files['summary'].write(f'  Total: ${total_cost:.4f}\n')
        
        # Close all files and mark as None
        for key, f in self.files.items():
            if f and not isinstance(f, type(None)):
                try:
                    f.close()
                except:
                    pass  # Already closed
                self.files[key] = None
