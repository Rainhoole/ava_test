'use client';

import {
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Download,
  FileCode,
  FileText,
  FileType,
  Loader2,
} from 'lucide-react';
import { ReportSections } from '@/components/report/ReportSections';
import { ReportSidebar } from '@/components/report/ReportSidebar';
import { ReportMarkdown } from '@/components/report/ReportMarkdown';
import { useReportViewer } from '@/hooks/useReportViewer';

interface ReportViewerProps {
  taskId: string;
}

export default function ReportViewer({ taskId }: ReportViewerProps) {
  const {
    report,
    structured,
    rawContent,
    hasStructuredSections,
    score,
    isLoading,
    error,
    copied,
    showDownloadMenu,
    isPdfGenerating,
    activeSectionId,
    openSectionId,
    contentRef,
    scrollContainerRef,
    dropdownRef,
    setShowDownloadMenu,
    setOpenSectionId,
    jumpToSection,
    handleDownloadMarkdown,
    handleDownloadPdf,
    handleCopy,
  } = useReportViewer(taskId);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-black">
        <div className="text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-gray-500" />
          <span className="text-sm text-gray-500">Loading report...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center bg-black">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-white/5">
            <FileText className="h-6 w-6 text-gray-500" />
          </div>
          <p className="font-medium text-white">Failed to load report</p>
          <p className="mt-1 text-sm text-gray-500">{error}</p>
        </div>
      </div>
    );
  }

  if (!rawContent) {
    return (
      <div className="flex flex-1 items-center justify-center bg-black text-gray-500">
        <div className="text-center">
          <FileText className="mx-auto mb-4 h-8 w-8 text-gray-600" />
          <span className="text-sm">Report not available yet</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative z-20 border-b border-white/[0.06] bg-black/80 px-4 py-3 backdrop-blur-xl md:px-8">
        <div className="mx-auto flex w-full max-w-[1500px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="h-4 w-4 flex-shrink-0 text-gray-500" />
            <span className="truncate text-sm font-medium text-gray-200">{report?.report?.filename}</span>
            <span className="font-mono text-xs text-gray-600">
              ({((report?.report?.size_bytes ?? 0) / 1024).toFixed(1)} KB)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-gray-400 transition-all hover:bg-white/5 hover:text-white"
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4 text-brand-blue" />
                  <span className="text-brand-blue">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-4 w-4" />
                  <span>Copy</span>
                </>
              )}
            </button>

            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                disabled={isPdfGenerating}
                className="flex items-center gap-2 rounded-lg bg-brand-blue px-3 py-1.5 text-sm text-black transition-all hover:bg-brand-blue-hover disabled:opacity-50"
              >
                {isPdfGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    <span>Download</span>
                    <ChevronDown className="h-3 w-3" />
                  </>
                )}
              </button>

              {showDownloadMenu && (
                <div className="absolute right-0 z-50 mt-2 w-48 rounded-lg border border-white/10 bg-[#141414] py-1 shadow-lg">
                  <button
                    onClick={handleDownloadMarkdown}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5"
                  >
                    <FileCode className="h-4 w-4 text-gray-500" />
                    <div className="text-left">
                      <div className="font-medium">Markdown</div>
                      <div className="text-xs text-gray-500">.md source file</div>
                    </div>
                  </button>
                  <button
                    onClick={handleDownloadPdf}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:bg-white/5"
                  >
                    <FileType className="h-4 w-4 text-gray-500" />
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

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto bg-black">
        <div className="report-enhanced px-4 py-8 md:px-8 xl:px-12">
          <div className="mx-auto w-full max-w-[1500px] xl:grid xl:grid-cols-[minmax(0,1fr)_320px] xl:gap-8">
            <div ref={contentRef} className="min-w-0 space-y-5">
              <section className="rb-hero">
                <div className="rb-hero-pill">
                  <BookOpen className="h-4 w-4" />
                  <span>Deal Brief</span>
                </div>
                <h1>{structured.title}</h1>
                <div className="rb-meta-panel">
                  <div className="rb-card-header">
                    <h3>Metadata</h3>
                  </div>
                  <div className="rb-meta-grid">
                    <div>
                      <span>Score</span>
                      <strong>{score || 'N/A'}</strong>
                    </div>
                    {structured.metadata.stage && (
                      <div>
                        <span>Stage</span>
                        <strong>{structured.metadata.stage}</strong>
                      </div>
                    )}
                    {structured.metadata.confidence && (
                      <div>
                        <span>Confidence</span>
                        <strong>{structured.metadata.confidence}</strong>
                      </div>
                    )}
                    <div>
                      <span>Sources</span>
                      <strong>{structured.sources.length}</strong>
                    </div>
                  </div>
                </div>

                {structured.metadata.categories.length > 0 && (
                  <div className="rb-tag-wrap">
                    {structured.metadata.categories.map((category) => (
                      <span key={category} className="rb-tag">
                        {category}
                      </span>
                    ))}
                  </div>
                )}
              </section>

              {hasStructuredSections ? (
                <ReportSections
                  sections={structured.sections}
                  openSectionId={openSectionId}
                  onToggleSection={(sectionId) =>
                    setOpenSectionId((prev) => (prev === sectionId ? '' : sectionId))
                  }
                />
              ) : (
                <section className="rb-card">
                  <div className="rb-card-header">
                    <h2>Full Markdown Report</h2>
                    <span>fallback mode</span>
                  </div>
                  <ReportMarkdown content={structured.normalizedContent} />
                </section>
              )}
            </div>

            <aside className="hidden xl:block">
              <ReportSidebar
                hasStructuredSections={hasStructuredSections}
                sections={structured.sections}
                activeSectionId={activeSectionId}
                scoring={structured.scoring}
                timeline={structured.timeline}
                sources={structured.sources}
                onJumpToSection={jumpToSection}
              />
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
