import { useEffect, useMemo, useRef, useState } from 'react';
import { downloadReport, fetchReport } from '@/lib/api';
import { copyTextToClipboard, downloadMarkdownBlob, exportElementToPdf } from '@/lib/reportActions';
import { parseStructuredReport } from '@/lib/reportParser';
import type { ReportResponse } from '@/types';

export function useReportViewer(taskId: string) {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [isPdfGenerating, setIsPdfGenerating] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState('');
  const [openSectionId, setOpenSectionId] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    const loadReport = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const nextReport = await fetchReport(taskId);
        if (active) {
          setReport(nextReport);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load report');
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void loadReport();

    return () => {
      active = false;
    };
  }, [taskId]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDownloadMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const rawContent = report?.report?.content ?? '';
  const structured = useMemo(() => parseStructuredReport(rawContent), [rawContent]);
  const hasStructuredSections = structured.sections.length > 0;
  const score = structured.metadata.score ?? 0;

  useEffect(() => {
    if (!hasStructuredSections) {
      setOpenSectionId('');
      setActiveSectionId('');
      return;
    }

    const overviewSection =
      structured.sections.find((section) => /overview/i.test(section.title)) ?? structured.sections[0];

    if (!overviewSection) {
      return;
    }

    setOpenSectionId((prev) => prev || overviewSection.id);
    setActiveSectionId((prev) => prev || overviewSection.id);
  }, [hasStructuredSections, structured.sections]);

  useEffect(() => {
    if (!hasStructuredSections) {
      return;
    }

    const root = scrollContainerRef.current;
    if (!root) {
      return;
    }

    const elements = structured.sections
      .map((section) => document.getElementById(section.id))
      .filter((element): element is HTMLElement => Boolean(element));

    if (elements.length === 0) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible[0]) {
          setActiveSectionId(visible[0].target.id);
        }
      },
      {
        root,
        rootMargin: '-16% 0px -70% 0px',
        threshold: [0, 1],
      }
    );

    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [hasStructuredSections, structured.sections]);

  const jumpToSection = (sectionId: string) => {
    const root = scrollContainerRef.current;
    const target = document.getElementById(sectionId);

    if (!root || !target) {
      return;
    }

    root.scrollTo({ top: Math.max(0, target.offsetTop - 88), behavior: 'smooth' });
    setActiveSectionId(sectionId);
    setOpenSectionId(sectionId);
  };

  const handleDownloadMarkdown = async () => {
    try {
      const blob = await downloadReport(taskId);
      downloadMarkdownBlob(blob, report?.report?.filename || `${taskId}_report.md`);
    } catch (err) {
      console.error('Download failed:', err);
    }

    setShowDownloadMenu(false);
  };

  const handleDownloadPdf = async () => {
    if (!contentRef.current || !rawContent) {
      return;
    }

    setIsPdfGenerating(true);
    setShowDownloadMenu(false);

    try {
      const filename = (report?.report?.filename || `${taskId}_report.md`).replace('.md', '.pdf');
      await exportElementToPdf(contentRef.current, filename);
    } catch (err) {
      console.error('PDF generation failed:', err);
    } finally {
      setIsPdfGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!rawContent) {
      return;
    }

    try {
      await copyTextToClipboard(rawContent);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  return {
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
  };
}
