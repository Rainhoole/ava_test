import type { LogEntry } from '@/types';

export interface ParsedLogRecord {
  raw: string;
  entry: LogEntry | null;
}

/**
 * 解析 JSONL 日志；旧格式日志返回 null，交给纯文本兜底渲染。
 */
export function parseLogLine(line: string): LogEntry | null {
  try {
    const entry = JSON.parse(line);
    if (entry && typeof entry.type === 'string' && typeof entry.seq === 'number') {
      return entry as LogEntry;
    }
    return null;
  } catch {
    return null;
  }
}
