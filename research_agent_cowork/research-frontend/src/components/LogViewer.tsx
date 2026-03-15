'use client';

import { useDeferredValue, useEffect, useRef, useState } from 'react';
import { ArrowDown, Info, Loader2 } from 'lucide-react';
import { LegacyLogMessage } from '@/components/logs/LegacyLogMessage';
import { StructuredLogMessage } from '@/components/logs/StructuredLogMessage';
import { useLogStream } from '@/hooks/useLogStream';
import type { LogEntry } from '@/types';

interface LogViewerProps {
  taskId?: string;
  isRunning: boolean;
  extraEntries?: LogEntry[];
}

export default function LogViewer({ taskId, isRunning, extraEntries = [] }: LogViewerProps) {
  const [showScrollButton, setShowScrollButton] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const isAwaitingAuth = !taskId && isRunning;
  const { combinedLogs, isConnected, isStructured, totalEntries } = useLogStream(taskId, extraEntries);
  const deferredLogs = useDeferredValue(combinedLogs);

  useEffect(() => {
    if (autoScrollRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [deferredLogs]);

  const handleScroll = () => {
    if (!containerRef.current) {
      return;
    }

    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    autoScrollRef.current = isAtBottom;
    setShowScrollButton(!isAtBottom && totalEntries > 10);
  };

  const scrollToBottom = () => {
    if (!containerRef.current) {
      return;
    }

    containerRef.current.scrollTop = containerRef.current.scrollHeight;
    autoScrollRef.current = true;
    setShowScrollButton(false);
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="border-b border-white/[0.06] bg-black px-8 py-3">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between">
          <div className="flex items-center gap-2">
            {isAwaitingAuth ? (
              <>
                <div className="h-2 w-2 rounded-full bg-gray-600" />
                <span className="text-sm text-gray-500">Awaiting authorization</span>
              </>
            ) : isRunning && isConnected ? (
              <>
                <div className="relative">
                  <div className="h-2 w-2 rounded-full bg-brand-blue" />
                  <div className="absolute inset-0 h-2 w-2 rounded-full bg-brand-blue animate-ping" />
                </div>
                <span className="text-sm font-medium text-brand-blue">Live</span>
              </>
            ) : isRunning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
                <span className="text-sm font-medium text-gray-400">Connecting...</span>
              </>
            ) : (
              <>
                <div className="h-2 w-2 rounded-full bg-gray-600" />
                <span className="text-sm text-gray-500">Completed</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            {isStructured && (
              <span className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-xs text-gray-400">
                JSONL
              </span>
            )}
            <span className="font-mono text-xs text-gray-600">{totalEntries} ENTRIES</span>
          </div>
        </div>
      </div>

      <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        <div className="px-4 py-6 md:px-8 lg:px-16">
          <div className="mx-auto max-w-4xl">
            {deferredLogs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                {isRunning ? (
                  <>
                    <Loader2 className="mb-4 h-8 w-8 animate-spin" />
                    <span className="text-sm">Waiting for agent activity...</span>
                  </>
                ) : (
                  <>
                    <Info className="mb-4 h-8 w-8" />
                    <span className="text-sm">No logs available</span>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {deferredLogs.map((log, index) =>
                  log.entry ? (
                    <StructuredLogMessage key={`${log.entry.seq}-${index}`} entry={log.entry} index={index} />
                  ) : (
                    <LegacyLogMessage key={`legacy-${index}`} line={log.raw} index={index} />
                  )
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-6 right-6 rounded-full bg-brand-blue p-3 text-black shadow-lg transition-all hover:scale-105 hover:bg-brand-blue-hover"
        >
          <ArrowDown className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
