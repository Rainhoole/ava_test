import {
  AlertCircle,
  Bot,
  CheckCircle,
  Flag,
  Info,
  Play,
  Settings,
  Sparkles,
  Terminal,
  User,
  Wallet,
  Wrench,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  AppLogEntry,
  AssistantTextEntry,
  AssistantThinkingEntry,
  BudgetEntry,
  ErrorEntry,
  LogEntry,
  LogEntryType,
  ResultEntry,
  SessionEndEntry,
  SessionStartEntry,
  SystemEntry,
  ToolCallEntry,
  ToolResultEntry,
} from '@/types';

function getEntryConfig(type: LogEntryType) {
  switch (type) {
    case 'session_start':
      return {
        icon: Play,
        label: 'Session Start',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'session_end':
      return {
        icon: Flag,
        label: 'Session End',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'app':
      return {
        icon: Terminal,
        label: 'App',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'user_message':
    case 'user_text':
      return {
        icon: User,
        label: 'User',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'assistant_text':
      return {
        icon: Bot,
        label: 'Assistant',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'assistant_thinking':
      return {
        icon: Sparkles,
        label: 'Thinking',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-300',
        labelClass: 'text-gray-500',
      };
    case 'tool_call':
      return {
        icon: Wrench,
        label: 'Tool Call',
        containerClass: '',
        iconClass: 'text-gray-600',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500',
      };
    case 'tool_result':
      return {
        icon: CheckCircle,
        label: 'Tool Result',
        containerClass: '',
        iconClass: 'text-gray-600',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500',
      };
    case 'system':
      return {
        icon: Settings,
        label: 'System',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'budget':
      return {
        icon: Wallet,
        label: 'Budget',
        containerClass: '',
        iconClass: 'text-brand-blue',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'result':
      return {
        icon: Zap,
        label: 'Result',
        containerClass: '',
        iconClass: 'text-brand-blue',
        textClass: 'text-gray-200',
        labelClass: 'text-gray-500',
      };
    case 'error':
      return {
        icon: AlertCircle,
        label: 'Error',
        containerClass: '',
        iconClass: 'text-red-400',
        textClass: 'text-red-300',
        labelClass: 'text-red-400',
      };
    default:
      return {
        icon: Info,
        label: 'Info',
        containerClass: '',
        iconClass: 'text-gray-500',
        textClass: 'text-gray-400',
        labelClass: 'text-gray-500',
      };
  }
}

function renderEntryContent(entry: LogEntry) {
  switch (entry.type) {
    case 'session_start': {
      const session = entry as SessionStartEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">Research started for {session.target}</div>
          <div className="text-xs opacity-70">
            Version: {session.version} | Model: {session.model}
            {session.skill && ` | Skill: ${session.skill}`}
          </div>
        </div>
      );
    }

    case 'session_end': {
      const session = entry as SessionEndEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">Session {session.success ? 'completed' : 'failed'}</div>
          <div className="text-xs opacity-70">
            Duration: {session.duration_seconds.toFixed(1)}s | Cost: ${session.cost_usd.toFixed(4)}
          </div>
          {session.error && <div className="mt-1 text-xs text-red-400">Error: {session.error}</div>}
        </div>
      );
    }

    case 'app': {
      const appEntry = entry as AppLogEntry;
      const levelColors: Record<string, string> = {
        info: 'text-gray-300',
        debug: 'text-gray-500',
        warn: 'text-amber-400',
        error: 'text-red-400',
      };
      return <span className={levelColors[appEntry.level] || 'text-gray-400'}>[{appEntry.level.toUpperCase()}] {appEntry.message}</span>;
    }

    case 'user_message':
    case 'user_text':
      return <div className="whitespace-pre-wrap">{(entry as { content: string }).content}</div>;

    case 'assistant_text': {
      const assistantEntry = entry as AssistantTextEntry;
      return <div className="whitespace-pre-wrap">{assistantEntry.content}</div>;
    }

    case 'assistant_thinking': {
      const assistantEntry = entry as AssistantThinkingEntry;
      return <div className="whitespace-pre-wrap text-sm text-gray-400">{assistantEntry.content}</div>;
    }

    case 'tool_call': {
      const toolCall = entry as ToolCallEntry;
      return (
        <details className="cursor-pointer">
          <summary className="flex items-center gap-2 font-medium text-gray-300">
            <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-xs font-mono text-gray-300">
              {toolCall.tool}
            </span>
            <span className="text-xs font-mono opacity-50">{toolCall.tool_use_id.slice(0, 12)}...</span>
          </summary>
          <pre className="mt-2 max-h-40 overflow-x-auto rounded border border-white/10 bg-white/5 p-2 text-xs text-gray-300">
            {JSON.stringify(toolCall.input, null, 2)}
          </pre>
        </details>
      );
    }

    case 'tool_result': {
      const toolResult = entry as ToolResultEntry;
      const truncatedOutput =
        toolResult.output.length > 500 ? `${toolResult.output.slice(0, 500)}...` : toolResult.output;
      return (
        <details className="cursor-pointer">
          <summary className="flex items-center gap-2 font-medium text-gray-300">
            <span
              className={cn(
                'rounded border border-white/10 px-2 py-0.5 text-xs',
                toolResult.is_error ? 'bg-red-500/10 text-red-400' : 'bg-white/5 text-gray-300'
              )}
            >
              {toolResult.is_error ? 'ERROR' : 'OK'}
            </span>
            <span className="text-xs font-mono opacity-50">{toolResult.tool_use_id.slice(0, 12)}...</span>
            <span className="text-xs text-gray-500">Output ({toolResult.output.length} chars)</span>
          </summary>
          <pre className="mt-2 max-h-40 overflow-x-auto whitespace-pre-wrap rounded border border-white/10 bg-white/5 p-2 text-xs text-gray-300">
            {truncatedOutput}
          </pre>
        </details>
      );
    }

    case 'system': {
      const systemEntry = entry as SystemEntry;
      return (
        <div className="space-y-1">
          <div className="font-medium">{systemEntry.subtype}</div>
          <pre className="max-h-32 overflow-x-auto rounded border border-white/10 bg-white/5 p-2 text-xs text-gray-300">
            {JSON.stringify(systemEntry.data, null, 2)}
          </pre>
        </div>
      );
    }

    case 'budget': {
      const budgetEntry = entry as BudgetEntry;
      const actionStyles = {
        primary: 'bg-brand-blue text-black hover:bg-brand-blue-hover',
        secondary: 'border border-white/10 bg-white/5 text-gray-300 hover:bg-white/10',
        ghost: 'text-gray-400 hover:bg-white/5 hover:text-white',
      } as const;

      return (
        <div className="space-y-3">
          <div className="whitespace-pre-wrap">{budgetEntry.content}</div>
          {budgetEntry.actions && budgetEntry.actions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {budgetEntry.actions.map((action) => {
                const variant = action.variant ?? 'secondary';
                return (
                  <button
                    key={action.id}
                    onClick={action.onClick}
                    disabled={action.disabled}
                    className={cn(
                      'rounded-xl px-4 py-2 text-sm font-medium transition-colors',
                      actionStyles[variant],
                      action.disabled && 'cursor-not-allowed opacity-50'
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
      const resultEntry = entry as ResultEntry;
      return (
        <div className="space-y-2">
          <div className="flex items-center gap-2 font-medium">
            <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-xs text-gray-300">
              {resultEntry.subtype}
            </span>
            <span className="text-xs opacity-50">
              {resultEntry.num_turns} turns | {resultEntry.duration_ms}ms
              {resultEntry.cost_usd !== null && ` | $${resultEntry.cost_usd.toFixed(4)}`}
            </span>
          </div>
          {resultEntry.result && (
            <details className="cursor-pointer">
              <summary className="text-xs text-gray-500">Show result</summary>
              <pre className="mt-1 max-h-60 overflow-x-auto whitespace-pre-wrap rounded border border-white/10 bg-white/5 p-2 text-xs text-gray-300">
                {resultEntry.result}
              </pre>
            </details>
          )}
        </div>
      );
    }

    case 'error': {
      const errorEntry = entry as ErrorEntry;
      return <div className="font-medium">{errorEntry.message}</div>;
    }

    default:
      return <pre className="overflow-x-auto text-xs">{JSON.stringify(entry, null, 2)}</pre>;
  }
}

export function StructuredLogMessage({ entry, index }: { entry: LogEntry; index: number }) {
  const config = getEntryConfig(entry.type);
  const Icon = config.icon;
  const isPlainText = entry.type === 'assistant_text' || entry.type === 'assistant_thinking';

  return (
    <div
      className={cn(
        'animate-in fade-in slide-in-from-bottom-2 rounded-2xl p-4 transition-all',
        config.containerClass
      )}
      style={{ animationDelay: `${Math.min(index * 20, 500)}ms` }}
    >
      <div className="flex items-start gap-3">
        {!isPlainText && (
          <div className={cn('flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg', config.iconClass)}>
            <Icon className="h-4 w-4" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          {!isPlainText && (
            <div className="mb-1 flex items-center gap-2">
              <span className={cn('text-xs font-semibold uppercase tracking-wider', config.labelClass)}>
                {config.label}
              </span>
              {entry.ts && <span className="font-mono text-xs text-gray-600">{entry.ts}</span>}
              <span className="font-mono text-xs text-gray-700">#{entry.seq}</span>
            </div>
          )}
          <div className={cn('text-sm leading-relaxed', config.textClass)}>{renderEntryContent(entry)}</div>
        </div>
      </div>
    </div>
  );
}
