export function LegacyLogMessage({ line, index }: { line: string; index: number }) {
  return (
    <div
      className="animate-in fade-in rounded-xl border border-white/10 bg-white/[0.03] p-3 font-mono text-xs text-gray-400"
      style={{ animationDelay: `${Math.min(index * 20, 500)}ms` }}
    >
      {line}
    </div>
  );
}
