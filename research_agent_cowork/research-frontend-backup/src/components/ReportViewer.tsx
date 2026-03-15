'use client';

import { useEffect, useState, useRef } from 'react';
import { Loader2, Download, Copy, Check, FileText, ChevronDown, FileCode, FileType, Lock } from 'lucide-react';
import { fetchReport, downloadReport } from '@/lib/api';
import { ReportResponse } from '@/types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

import { PaymentStatus } from '@/types';

interface ReportViewerProps {
  taskId: string;
  paymentStatus?: PaymentStatus;
}

interface ReportMetadata {
  [key: string]: string;
}

// Extract domain from URL for display (e.g. "https://example.com/path" -> "example.com")
function extractDomain(url: string): string {
  try {
    const hostname = new URL(url).hostname;
    return hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

// Extract all unique sources from various citation formats
function extractSources(content: string): { label: string; url: string }[] {
  const sourceMap = new Map<string, string>();

  // Pattern 1: 【[description](URL)】
  const mdLinkRegex = /【\[([^\]]+)\]\(([^)]+)\)】/g;
  let match;
  while ((match = mdLinkRegex.exec(content)) !== null) {
    const url = match[2];
    if (!sourceMap.has(url)) {
      const label = match[1];
      const isUrl = /^https?:\/\//.test(label);
      sourceMap.set(url, isUrl ? extractDomain(label) : label);
    }
  }

  // Pattern 2: 【(URL)】 or 【(domain)】
  const parenRegex = /【\(([^)]+)\)】/g;
  while ((match = parenRegex.exec(content)) !== null) {
    const inner = match[1].trim();
    if (/^https?:\/\//.test(inner)) {
      if (!sourceMap.has(inner)) {
        sourceMap.set(inner, extractDomain(inner));
      }
    }
  }

  // Pattern 3: 【bare URL】
  const bareUrlRegex = /【\s*(https?:\/\/[^\s】]+)\s*】/g;
  while ((match = bareUrlRegex.exec(content)) !== null) {
    const url = match[1];
    if (!sourceMap.has(url)) {
      sourceMap.set(url, extractDomain(url));
    }
  }

  return Array.from(sourceMap.entries()).map(([url, label]) => ({ label, url }));
}

// Clean up all citation bracket formats for cleaner inline display
function cleanCitations(content: string): string {
  // 1. 【[text](URL)】 → [text](URL) — already a markdown link, remove lenticular brackets
  content = content.replace(
    /【\[([^\]]+)\]\(([^)]+)\)】/g,
    (_match, label: string, url: string) => {
      // Shorten display text if it's a raw URL
      const isUrl = /^https?:\/\//.test(label);
      return `[${isUrl ? extractDomain(label) : label}](${url})`;
    }
  );

  // 2. 【(URL)】 → [domain](URL) — URL in parens, convert to clean link
  content = content.replace(
    /【\((https?:\/\/[^)]+)\)】/g,
    (_match, url: string) => `[${extractDomain(url)}](${url})`
  );

  // 3. 【(source_label)】 → (source_label) — non-URL in parens, remove outer brackets
  content = content.replace(/【\(([^)]*)\)】/g, '($1)');

  // 4. 【number†source】 or 【number:number†source】 — OpenAI internal citation markers, remove
  content = content.replace(/【\d+(?::\d+)?†[^】]*】/g, '');

  // 5. 【bare URL】 → [domain](URL)
  content = content.replace(
    /【\s*(https?:\/\/[^\s】]+)\s*】/g,
    (_match, url: string) => `[${extractDomain(url)}](${url})`
  );

  // 6. 【remaining text】 → remove brackets, keep text
  content = content.replace(/【([^】]*)】/g, '$1');

  return content;
}

// Parse report content to extract metadata and process sections
function parseReportContent(content: string): { metadata: ReportMetadata; processedContent: string; sources: { label: string; url: string }[] } {
  const metadata: ReportMetadata = {};
  let processedContent = content;

  // 0) Extract sources before any processing
  const sources = extractSources(content);

  // 1) Extract META_ key-value pairs after === REPORT START ===
  const reportStartMatch = content.match(/=== REPORT START ===([\s\S]*?)(?==== SECTION:)/);
  if (reportStartMatch) {
    const metaBlock = reportStartMatch[1];
    const metaRegex = /META_(\w+):\s*(.+)/g;
    let match;
    while ((match = metaRegex.exec(metaBlock)) !== null) {
      metadata[match[1]] = match[2].trim();
    }
    // Remove the entire metadata block (from REPORT START to first SECTION)
    processedContent = content.replace(/=== REPORT START ===[\s\S]*?(?==== SECTION:)/, '');
  }

  // 2) Process SECTION markers
  processedContent = processedContent
    .replace(/=== SECTION: .+? ===/g, '\n<div class="section-divider"></div>\n')
    .replace(/=== END SECTION ===/g, '')
    .replace(/=== REPORT END ===/g, '');

  // 3) Clean up citation brackets for cleaner inline display
  processedContent = cleanCitations(processedContent);

  return { metadata, processedContent, sources };
}

// Metadata badges component
function MetadataBadges({ metadata }: { metadata: ReportMetadata }) {
  const entries = Object.entries(metadata).filter(([key]) => key !== 'MONITOR');
  if (entries.length === 0) return null;

  const formatValue = (key: string, value: string): string => {
    if (key === 'CATEGORIES' && value.startsWith('[')) {
      try {
        const arr = JSON.parse(value);
        return arr.join(', ');
      } catch {
        return value;
      }
    }
    return value;
  };

  const formatKey = (key: string): string => {
    return key.charAt(0) + key.slice(1).toLowerCase();
  };

  return (
    <div className="report-metadata">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="px-3 py-1.5 rounded-lg border text-sm font-medium bg-white/5 text-gray-300 border-white/10"
        >
          <span className="text-xs opacity-60 mr-1.5">{formatKey(key)}:</span>
          <span>{formatValue(key, value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function ReportViewer({ taskId, paymentStatus }: ReportViewerProps) {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [isPdfGenerating, setIsPdfGenerating] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsLoading(true);
    setError(null);

    fetchReport(taskId)
      .then(setReport)
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [taskId]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDownloadMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleDownloadMd = async () => {
    try {
      const blob = await downloadReport(taskId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = report?.report?.filename || `${taskId}_report.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
    setShowDownloadMenu(false);
  };

  const handleDownloadPdf = async () => {
    if (!contentRef.current || !report?.report?.content) return;

    setIsPdfGenerating(true);
    setShowDownloadMenu(false);

    const container = document.createElement('div');
    container.style.position = 'absolute';
    container.style.left = '-9999px';
    container.style.top = '0';
    container.style.width = '860px';
    document.body.appendChild(container);

    try {
      const html2pdf = (await import('html2pdf.js')).default;
      const element = contentRef.current.cloneNode(true) as HTMLElement;

      element.style.padding = '40px';
      element.style.maxWidth = '800px';
      element.style.width = '800px';
      element.style.margin = '0 auto';
      element.style.background = '#ffffff';
      element.style.color = '#333333';

      // html2canvas ignores CSS class overrides on cloned elements,
      // so we must walk the DOM and force inline styles directly.
      const forceLight = (root: HTMLElement) => {
        const all = root.querySelectorAll('*') as NodeListOf<HTMLElement>;
        all.forEach((el) => {
          const tag = el.tagName.toLowerCase();
          const classes = el.className || '';

          // Metadata badges container
          if (classes.includes('report-metadata')) {
            el.style.background = '#f9fafb';
            el.style.borderColor = '#e5e7eb';
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }

          // Individual metadata badge items (direct children of report-metadata)
          if (el.parentElement?.className?.includes('report-metadata')) {
            el.style.background = '#f3f4f6';
            el.style.color = '#333333';
            el.style.borderColor = '#d1d5db';
          }

          // Spans inside metadata badges (label text)
          if (tag === 'span' && el.closest('.report-metadata')) {
            el.style.color = '#555555';
          }

          // Headings: dark text, serif fallback for PDF
          if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4') {
            el.style.color = '#111111';
            el.style.fontFamily = 'Georgia, "Times New Roman", serif';
            el.style.pageBreakAfter = 'avoid';
            el.style.breakAfter = 'avoid';
          }

          // Paragraphs
          if (tag === 'p') {
            el.style.color = '#333333';
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }

          // List items
          if (tag === 'li') {
            el.style.color = '#333333';
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }

          // Lists
          if (tag === 'ul' || tag === 'ol') {
            el.style.color = '#333333';
          }

          // Bold / strong
          if (tag === 'strong' || tag === 'b') {
            el.style.color = '#111111';
          }

          // Links
          if (tag === 'a') {
            el.style.color = '#2563eb';
          }

          // Inline code
          if (tag === 'code' && el.parentElement?.tagName.toLowerCase() !== 'pre') {
            el.style.background = '#f3f4f6';
            el.style.color = '#0369a1';
          }

          // Code blocks
          if (tag === 'pre') {
            el.style.background = '#f8fafc';
            el.style.color = '#1e293b';
            el.style.borderColor = '#e2e8f0';
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }
          if (tag === 'code' && el.parentElement?.tagName.toLowerCase() === 'pre') {
            el.style.background = 'transparent';
            el.style.color = '#1e293b';
          }

          // Table
          if (tag === 'table') {
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }
          if (tag === 'th') {
            el.style.color = '#111111';
            el.style.borderColor = '#d1d5db';
            el.style.background = '#f9fafb';
          }
          if (tag === 'td') {
            el.style.color = '#333333';
            el.style.borderColor = '#d1d5db';
          }
          if (tag === 'thead') {
            el.style.background = '#f9fafb';
          }

          // Blockquote
          if (tag === 'blockquote') {
            el.style.color = '#4b5563';
            el.style.borderColor = '#2563eb';
            el.style.background = 'rgba(37,99,235,0.05)';
            el.style.pageBreakInside = 'avoid';
            el.style.breakInside = 'avoid';
          }

          // HR
          if (tag === 'hr') {
            el.style.borderColor = '#e5e7eb';
          }

          // Section divider
          if (classes.includes('section-divider')) {
            el.style.borderColor = '#e5e7eb';
          }

          // Sources section
          if (classes.includes('sources-section')) {
            el.style.borderColor = 'rgba(37,99,235,0.2)';
          }

          // ::before pseudo-elements can't be styled inline,
          // hide them by removing the flex gap trick on h1
          if (tag === 'h1') {
            el.style.borderBottomColor = '#e5e7eb';
          }
        });
      };

      forceLight(element);
      container.appendChild(element);

      const filename = (report?.report?.filename || `${taskId}_report.md`).replace('.md', '.pdf');

      const opt = {
        margin: [15, 10, 15, 10] as [number, number, number, number],
        filename: filename,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: {
          scale: 2,
          useCORS: true,
          letterRendering: true,
          backgroundColor: '#ffffff'
        },
        jsPDF: {
          unit: 'mm',
          format: 'a4',
          orientation: 'portrait' as const
        },
        pagebreak: {
          mode: ['css', 'legacy'] as const,
          before: '.page-break-before',
          after: '.page-break-after',
          avoid: ['pre', 'blockquote', 'table', 'img', '.report-metadata', 'h1', 'h2', 'h3', 'h4']
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (html2pdf() as any).set(opt).from(element).save();
    } catch (err) {
      console.error('PDF generation failed:', err);
    } finally {
      document.body.removeChild(container);
      setIsPdfGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!report?.report?.content) return;
    try {
      await navigator.clipboard.writeText(report.report.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-gray-500 mx-auto mb-4" />
          <span className="text-sm text-gray-500">Loading report...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <FileText className="w-6 h-6 text-gray-500" />
          </div>
          <p className="text-white font-medium">Failed to load report</p>
          <p className="text-sm text-gray-500 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  if (!report?.report?.content) {
    return (
      <div className="flex-1 flex items-center justify-center bg-black text-gray-500">
        <div className="text-center">
          <FileText className="w-8 h-8 text-gray-600 mx-auto mb-4" />
          <span className="text-sm">Report not available yet</span>
        </div>
      </div>
    );
  }

  if (paymentStatus === 'failed') {
    return (
      <div className="flex-1 flex items-center justify-center bg-black">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto mb-5">
            <Lock className="w-8 h-8 text-red-400" />
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">Report Locked</h3>
          <p className="text-sm text-gray-400 leading-relaxed">
            Payment failed for this research task. Please retry the payment using the Budget panel below to unlock the report and download options.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-8 py-3 border-b border-white/[0.06] bg-black">
        <div className="max-w-4xl mx-auto w-full flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-300 font-medium">
              {report.report.filename}
            </span>
            <span className="text-xs text-gray-600 font-mono">
              ({(report.report.size_bytes / 1024).toFixed(1)} KB)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-brand-blue" />
                  <span className="text-brand-blue">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span>Copy</span>
                </>
              )}
            </button>

            {/* Download dropdown */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                disabled={isPdfGenerating}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-brand-blue text-black hover:bg-brand-blue-hover rounded-lg transition-all disabled:opacity-50"
              >
                {isPdfGenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    <span>Download</span>
                    <ChevronDown className="w-3 h-3" />
                  </>
                )}
              </button>

              {showDownloadMenu && (
                <div className="absolute right-0 mt-2 w-48 bg-[#1A1A1A] rounded-lg shadow-lg border border-white/10 py-1 z-50">
                  <button
                    onClick={handleDownloadMd}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-300 hover:bg-white/5 transition-colors"
                  >
                    <FileCode className="w-4 h-4 text-gray-500" />
                    <div className="text-left">
                      <div className="font-medium">Markdown</div>
                      <div className="text-xs text-gray-500">.md source file</div>
                    </div>
                  </button>
                  <button
                    onClick={handleDownloadPdf}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-300 hover:bg-white/5 transition-colors"
                  >
                    <FileType className="w-4 h-4 text-gray-500" />
                    <div className="text-left">
                      <div className="font-medium">PDF</div>
                      <div className="text-xs text-gray-500">.pdf formatted document</div>
                    </div>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Report content with proper markdown rendering */}
      <div className="flex-1 overflow-y-auto bg-black">
        <div className="px-4 md:px-8 lg:px-16 py-8">
          {(() => {
            const { metadata, processedContent, sources } = parseReportContent(report.report.content);
            return (
              <div
                ref={contentRef}
                className="markdown-content max-w-4xl mx-auto prose prose-gray"
              >
                {/* Metadata badges */}
                <MetadataBadges metadata={metadata} />

                {/* Processed markdown content */}
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeRaw]}
                  components={{
                    a: ({ href, children, ...props }) => (
                      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                        {children}
                      </a>
                    ),
                  }}
                >
                  {processedContent}
                </ReactMarkdown>

                {/* Aggregated Information Sources section */}
                {sources.length > 0 && (
                  <div className="sources-section">
                    <h2>Information Sources</h2>
                    <ol>
                      {sources.map((source, index) => (
                        <li key={index}>
                          <a href={source.url} target="_blank" rel="noopener noreferrer">
                            {source.label}
                          </a>
                          <span className="source-url">{extractDomain(source.url)}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
