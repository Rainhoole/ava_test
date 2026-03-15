'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Loader2,
  ArrowDown,
  Bot,
  Wrench,
  CheckCircle,
  AlertCircle,
  Info,
  Sparkles,
  Terminal,
  User,
  Play,
  Flag,
  Zap,
  Settings,
  Wallet
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { createLogStream } from '@/lib/api';
import { cn } from '@/lib/utils';
import type {
  LogEntry,
  LogEntryType,
  ToolCallEntry,
  ToolResultEntry,
  AssistantTextEntry,
  AssistantThinkingEntry,
  AppLogEntry,
  SessionStartEntry,
  SessionEndEntry,
  SystemEntry,
  ResultEntry,
  ErrorEntry,
  BudgetEntry
} from '@/types';

interface LogViewerProps {
  taskId?: string;
  isRunning: boolean;
  extraEntries?: LogEntry[];
}

/**
 * Parse a JSONL line into a LogEntry.
 * Returns null if parsing fails (legacy text format).
 */
function parseLogLine(line: string): LogEntry | null {
  try {
    const entry = JSON.parse(line);
    // Validate it has required fields
    if (entry && typeof entry.type === 'string' && typeof entry.seq === 'number') {
      return entry as LogEntry;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Get display configuration for each log entry type.
 */
function getEntryConfig(type: LogEntryType) {
  switch (type) {
    case 'session_start':
      return {
        icon: Play,
        label: 'Session Start',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'session_end':
      return {
        icon: Flag,
        label: 'Session End',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'app':
      return {
        icon: Terminal,
        label: 'App',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'user_message':
    case 'user_text':
      return {
        icon: User,
        label: 'User',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'assistant_text':
      return {
        icon: Bot,
        label: 'Assistant',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'assistant_thinking':
      return {
        icon: Sparkles,
        label: 'Thinking',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-300',
        labelClass: 'text-gray-500'
      };
    case 'tool_call':
      return {
        icon: Wrench,
        label: 'Tool Call',
        containerClass: '',
        iconClass: 'text-gray-600',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500'
      };
    case 'tool_result':
      return {
        icon: CheckCircle,
        label: 'Tool Result',
        containerClass: '',
        iconClass: 'text-gray-600',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500'
      };
    case 'system':
      return {
        icon: Settings,
        label: 'System',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'budget':
      return {
        icon: Wallet,
        label: 'Budget',
        containerClass: '',
        iconClass: 'text-brand-blue',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'result':
      return {
        icon: Zap,
        label: 'Result',
        containerClass: '',
        iconClass: 'text-brand-blue',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500'
      };
    case 'error':
      return {
        icon: AlertCircle,
        label: 'Error',
        containerClass: '',
        iconClass: 'text-red-400',
        textClass: 'text-red-300',
        labelClass: 'text-red-400'
      };
    default:
      return {
        icon: Info,
        label: 'Info',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500'
      };
  }
}

/**
 * Render content based on entry type.
 */
function renderEntryContent(entry: LogEntry) {
  switch (entry.type) {
    case 'session_start': {
      const e = entry as SessionStartEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">Research started for {e.target}</div>
          <div className="text-xs opacity-70">
            Version: {e.version} | Model: {e.model}
            {e.skill && ` | Skill: ${e.skill}`}
          </div>
        </div>
      );
    }

    case 'session_end': {
      const e = entry as SessionEndEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">
            Session {e.success ? 'completed' : 'failed'}
          </div>
          <div className="text-xs opacity-70">
            Duration: {e.duration_seconds.toFixed(1)}s |
            Cost: ${e.cost_usd.toFixed(4)}
          </div>
          {e.error && (
            <div className="text-xs text-red-400 mt-1">Error: {e.error}</div>
          )}
        </div>
      );
    }

    case 'app': {
      const e = entry as AppLogEntry;
      const levelColors: Record<string, string> = {
        info: 'text-gray-300',
        debug: 'text-gray-500',
        warn: 'text-amber-400',
        error: 'text-red-400'
      };
      return (
        <span className={levelColors[e.level] || 'text-gray-400'}>
          [{e.level.toUpperCase()}] {e.message}
        </span>
      );
    }

    case 'user_message':
    case 'user_text':
      return <div className="whitespace-pre-wrap">{(entry as { content: string }).content}</div>;

    case 'assistant_text': {
      const e = entry as AssistantTextEntry;
      return (
        <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed [&_strong]:text-white [&_em]:text-gray-300 [&_p]:my-1">
          <ReactMarkdown>{e.content}</ReactMarkdown>
        </div>
      );
    }

    case 'assistant_thinking': {
      const e = entry as AssistantThinkingEntry;
      return (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3">
          <div className="prose prose-sm prose-invert max-w-none text-sm text-gray-400 leading-relaxed [&_strong]:text-gray-300 [&_em]:text-gray-300 [&_p]:my-1">
            <ReactMarkdown>{e.content}</ReactMarkdown>
          </div>
        </div>
      );
    }

    case 'tool_call': {
      const e = entry as ToolCallEntry;
      return (
        <details className="cursor-pointer">
          <summary className="font-medium flex items-center gap-2 text-gray-300">
            <span className="px-2 py-0.5 bg-white/5 rounded text-xs font-mono text-gray-300 border border-white/10">
              {e.tool}
            </span>
          </summary>
          <pre className="mt-2 text-xs bg-white/5 p-2 rounded overflow-x-auto max-h-40 border border-white/10 text-gray-300">
            {JSON.stringify(e.input, null, 2)}
          </pre>
        </details>
      );
    }

    case 'tool_result': {
      const e = entry as ToolResultEntry;
      const truncatedOutput = e.output.length > 500
        ? e.output.slice(0, 500) + '...'
        : e.output;
      return (
        <details className="cursor-pointer">
          <summary className="flex items-center gap-2 font-medium text-gray-300">
            <span className={cn(
              'px-2 py-0.5 rounded text-xs border border-white/10',
              e.is_error ? 'bg-red-500/10 text-red-400' : 'bg-white/5 text-gray-300'
            )}>
              {e.is_error ? 'ERROR' : 'OK'}
            </span>
            <span className="text-xs text-gray-500">Output ({e.output.length} chars)</span>
          </summary>
          <pre className="mt-2 text-xs bg-white/5 p-2 rounded overflow-x-auto max-h-40 whitespace-pre-wrap border border-white/10 text-gray-300">
            {truncatedOutput}
          </pre>
        </details>
      );
    }

    case 'system': {
      const e = entry as SystemEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">{e.subtype}</div>
          <pre className="text-xs bg-white/5 p-2 rounded overflow-x-auto max-h-32 border border-white/10 text-gray-300">
            {JSON.stringify(e.data, null, 2)}
          </pre>
        </div>
      );
    }

    case 'budget': {
      const e = entry as BudgetEntry;
      const actionStyles = {
        primary: 'bg-brand-blue text-black hover:bg-brand-blue-hover',
        secondary: 'bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10',
        ghost: 'text-gray-400 hover:text-white hover:bg-white/5'
      } as const;

      return (
        <div className="space-y-3">
          <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed [&_strong]:text-white [&_p]:my-1">
            <ReactMarkdown>{e.content}</ReactMarkdown>
          </div>
          {e.actions && e.actions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {e.actions.map((action) => {
                const variant = action.variant ?? 'secondary';
                return (
                  <button
                    key={action.id}
                    onClick={action.onClick}
                    disabled={action.disabled}
                    className={cn(
                      'px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                      actionStyles[variant],
                      action.disabled && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {action.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      );
    }

    case 'result': {
      const e = entry as ResultEntry;
      return (
        <div className="space-y-2">
          <div className="font-medium flex items-center gap-2">
            <span className={cn(
              'px-2 py-0.5 rounded text-xs bg-white/5 text-gray-300 border border-white/10'
            )}>
              {e.subtype}
            </span>
            <span className="text-xs opacity-50">
              {e.num_turns} turns | {e.duration_ms}ms
              {e.cost_usd !== null && ` | $${e.cost_usd.toFixed(4)}`}
            </span>
          </div>
          {e.result && (
            <details className="cursor-pointer">
              <summary className="text-xs text-gray-500">Show result</summary>
              <pre className="mt-1 text-xs bg-white/5 p-2 rounded overflow-x-auto max-h-60 whitespace-pre-wrap border border-white/10 text-gray-300">
                {e.result}
              </pre>
            </details>
          )}
        </div>
      );
    }

    case 'error': {
      const e = entry as ErrorEntry;
      return <div className="font-medium">{e.message}</div>;
    }

    default:
      // Handle unknown types
      return (
        <pre className="text-xs overflow-x-auto">
          {JSON.stringify(entry, null, 2)}
        </pre>
      );
  }
}

/**
 * Single log message component.
 */
function LogMessage({ entry, index }: { entry: LogEntry; index: number }) {
  const config = getEntryConfig(entry.type);
  const Icon = config.icon;
  const isPlainText = entry.type === 'assistant_text' || entry.type === 'assistant_thinking';

  return (
    <div
      className={cn(
        'rounded-2xl p-4 transition-all animate-in fade-in slide-in-from-bottom-2',
        config.containerClass
      )}
      style={{ animationDelay: `${Math.min(index * 20, 500)}ms` }}
    >
      <div className="flex items-start gap-3">
        {!isPlainText && (
          <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0', config.iconClass)}>
            <Icon className="w-4 h-4" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          {!isPlainText && (
            <div className="flex items-center gap-2 mb-1">
              <span className={cn('text-xs font-semibold uppercase tracking-wider', config.labelClass)}>
                {config.label}
              </span>
              {entry.ts && (
                <span className="text-xs text-gray-600 font-mono">
                  {entry.ts}
                </span>
              )}
              <span className="text-xs text-gray-700 font-mono">
                #{entry.seq}
              </span>
            </div>
          )}
          <div className={cn('text-sm leading-relaxed', config.textClass)}>
            {renderEntryContent(entry)}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Fallback component for legacy text logs.
 */
function LegacyLogMessage({ line, index }: { line: string; index: number }) {
  return (
    <div
      className="rounded-xl border border-white/10 bg-white/[0.03] p-3 font-mono text-xs text-gray-400 animate-in fade-in"
      style={{ animationDelay: `${Math.min(index * 20, 500)}ms` }}
    >
      {line}
    </div>
  );
}

export default function LogViewer({ taskId, isRunning, extraEntries = [] }: LogViewerProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const isAwaitingAuth = !taskId && isRunning;

  useEffect(() => {
    setLogs([]);
    setIsConnected(false);
    autoScrollRef.current = true;

    if (!taskId) {
      return;
    }

    let eventSource: EventSource | null = null;
    let cancelled = false;

    const initStream = async () => {
      try {
        const source = await createLogStream(taskId);
        if (cancelled) {
          source.close();
          return;
        }
        eventSource = source;

        eventSource.onopen = () => {
          setIsConnected(true);
        };

        eventSource.addEventListener('log', (event) => {
          setLogs((prev) => [...prev, event.data]);
        });

        eventSource.addEventListener('complete', () => {
          setIsConnected(false);
          eventSource?.close();
        });

        eventSource.onerror = () => {
          setIsConnected(false);
          eventSource?.close();
        };
      } catch (error) {
        console.error('Failed to open log stream:', error);
        setIsConnected(false);
      }
    };

    initStream();

    return () => {
      cancelled = true;
      eventSource?.close();
    };
  }, [taskId]);

  useEffect(() => {
    if (autoScrollRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, extraEntries]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    autoScrollRef.current = isAtBottom;
    setShowScrollButton(!isAtBottom && logs.length + extraEntries.length > 10);
  };

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
      autoScrollRef.current = true;
      setShowScrollButton(false);
    }
  };

  // Parse logs - try JSON first, fallback to legacy text
  const parsedLogs = logs.map((line) => ({
    raw: line,
    entry: parseLogLine(line)
  }));

  const combinedLogs = [
    ...extraEntries.map((entry) => ({ raw: '', entry })),
    ...parsedLogs
  ];

  // Count structured vs legacy
  const structuredCount = parsedLogs.filter(l => l.entry !== null).length;
  const isStructured = structuredCount > parsedLogs.length / 2;
  const totalEntries = logs.length + extraEntries.length;

  return (
    <div className="flex-1 flex flex-col min-h-0 relative">
      {/* Status bar */}
      <div className="flex items-center gap-3 px-8 py-3 border-b border-white/[0.06] bg-black">
        <div className="max-w-4xl mx-auto w-full flex items-center justify-between">
            <div className="flex items-center gap-2">
            {isAwaitingAuth ? (
              <>
                <div className="w-2 h-2 rounded-full bg-gray-600" />
                <span className="text-sm text-gray-500">Awaiting authorization</span>
              </>
            ) : isRunning && isConnected ? (
              <>
                <div className="relative">
                  <div className="w-2 h-2 rounded-full bg-brand-blue" />
                  <div className="absolute inset-0 w-2 h-2 rounded-full bg-brand-blue animate-ping" />
                </div>
                <span className="text-sm font-medium text-brand-blue">Live</span>
              </>
            ) : isRunning ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                <span className="text-sm font-medium text-gray-400">Connecting...</span>
              </>
            ) : (
              <>
                <div className="w-2 h-2 rounded-full bg-gray-600" />
                <span className="text-sm text-gray-500">Completed</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            {isStructured && (
              <span className="text-xs text-gray-400 bg-white/5 px-2 py-0.5 rounded border border-white/10">
                JSONL
              </span>
            )}
            <span className="text-xs text-gray-600 font-mono">{totalEntries} ENTRIES</span>
          </div>
        </div>
      </div>

      {/* Log content with padding */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        <div className="px-4 md:px-8 lg:px-16 py-6">
          <div className="max-w-4xl mx-auto">
            {combinedLogs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                {isRunning ? (
                  <>
                    <Loader2 className="w-8 h-8 animate-spin mb-4" />
                    <span className="text-sm">Waiting for agent activity...</span>
                  </>
                ) : taskId ? (
                  <>
                    <Loader2 className="w-8 h-8 animate-spin mb-4" />
                    <span className="text-sm">Loading log...</span>
                  </>
                ) : (
                  <>
                    <Info className="w-8 h-8 mb-4" />
                    <span className="text-sm">No logs available</span>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {combinedLogs.map((log, idx) => (
                  log.entry ? (
                    <LogMessage key={idx} entry={log.entry} index={idx} />
                  ) : (
                    <LegacyLogMessage key={idx} line={log.raw} index={idx} />
                  )
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Scroll to bottom button */}
      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-6 right-6 p-3 bg-brand-blue hover:bg-brand-blue-hover text-black rounded-full shadow-lg transition-all hover:scale-105"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
