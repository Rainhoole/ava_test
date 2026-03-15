import { useEffect, useMemo, useState } from 'react';
import { createLogStream } from '@/lib/api';
import { parseLogLine, type ParsedLogRecord } from '@/lib/logs';
import type { LogEntry } from '@/types';

export function useLogStream(taskId?: string, extraEntries: LogEntry[] = []) {
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    setLogs([]);
    setIsConnected(false);

    if (!taskId) {
      return;
    }

    let cancelled = false;
    let eventSource: EventSource | null = null;

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

    void initStream();

    return () => {
      cancelled = true;
      eventSource?.close();
    };
  }, [taskId]);

  const parsedLogs = useMemo<ParsedLogRecord[]>(
    () =>
      logs.map((raw) => ({
        raw,
        entry: parseLogLine(raw),
      })),
    [logs]
  );

  const combinedLogs = useMemo<ParsedLogRecord[]>(
    () => [...extraEntries.map((entry) => ({ raw: '', entry })), ...parsedLogs],
    [extraEntries, parsedLogs]
  );

  const structuredCount = parsedLogs.filter((item) => item.entry !== null).length;

  return {
    combinedLogs,
    isConnected,
    isStructured: structuredCount > parsedLogs.length / 2,
    totalEntries: logs.length + extraEntries.length,
  };
}
