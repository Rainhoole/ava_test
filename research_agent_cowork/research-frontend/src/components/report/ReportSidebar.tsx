import { Calendar, Link2, ShieldAlert } from 'lucide-react';
import type { ScoreBreakdownItem, SourceItem, StructuredSection, TimelineEvent } from '@/types';

interface ReportSidebarProps {
  hasStructuredSections: boolean;
  sections: StructuredSection[];
  activeSectionId: string;
  scoring: ScoreBreakdownItem[];
  timeline: TimelineEvent[];
  sources: SourceItem[];
  onJumpToSection: (sectionId: string) => void;
}

export function ReportSidebar({
  hasStructuredSections,
  sections,
  activeSectionId,
  scoring,
  timeline,
  sources,
  onJumpToSection,
}: ReportSidebarProps) {
  return (
    <div className="report-sidebar sticky top-6">
      {hasStructuredSections && (
        <div className="rb-card">
          <div className="rb-card-header">
            <h3>Contents</h3>
          </div>
          <div className="rb-toc-list">
            {sections.map((section) => (
              <button
                key={section.id}
                onClick={() => onJumpToSection(section.id)}
                className={`rb-toc-item ${activeSectionId === section.id ? 'is-active' : ''}`}
              >
                <span className="truncate">{section.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="rb-card">
        <div className="rb-card-header">
          <h3>Scoring</h3>
        </div>
        <div className="rb-score-list">
          {scoring.length === 0 && <div className="rb-empty">No scoring rows detected.</div>}
          {scoring.map((item) => (
            <div key={item.label} className="rb-score-row">
              <div className="rb-score-top">
                <span>{item.label}</span>
                <strong>
                  {item.score}/{item.max}
                </strong>
              </div>
              <div className="rb-score-track">
                <span style={{ width: `${Math.min(100, Math.max(3, Math.round(item.percentage)))}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rb-card">
        <div className="rb-card-header">
          <h3>Timeline</h3>
          <span>{timeline.length} events</span>
        </div>
        <div className="rb-timeline">
          {timeline.length === 0 && <div className="rb-empty">Timeline items not detected.</div>}
          {timeline.map((event, index) => (
            <div key={`${event.date}-${index}`} className="rb-timeline-item">
              <div className="rb-timeline-dot">
                {event.category === 'announcement' ? (
                  <ShieldAlert className="h-3 w-3" />
                ) : (
                  <Calendar className="h-3 w-3" />
                )}
              </div>
              <div>
                <strong>{event.date}</strong>
                <p>{event.event}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {sources.length > 0 && (
        <div className="rb-card">
          <div className="rb-card-header">
            <h3>Source Links</h3>
            <span>
              <Link2 className="mr-1 inline h-3 w-3" />
              quick access
            </span>
          </div>
          <div className="rb-source-mini">
            {sources.slice(0, 8).map((source) => (
              <a key={`${source.id}-mini`} href={source.url} target="_blank" rel="noopener noreferrer">
                <span>{source.id}</span>
                <span>{source.domain}</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
