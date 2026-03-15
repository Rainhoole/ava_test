import { ChevronRight } from 'lucide-react';
import { ReportMarkdown } from './ReportMarkdown';
import type { StructuredSection } from '@/types';

interface ReportSectionsProps {
  sections: StructuredSection[];
  openSectionId: string;
  onToggleSection: (sectionId: string) => void;
}

export function ReportSections({ sections, openSectionId, onToggleSection }: ReportSectionsProps) {
  return (
    <div className="space-y-3">
      {sections.map((section) => {
        const isOpen = openSectionId === section.id;

        return (
          <section id={section.id} key={section.id} className="rb-section">
            <button className="rb-section-toggle" onClick={() => onToggleSection(section.id)}>
              <div className="rb-section-heading">
                <h2>{section.title}</h2>
              </div>
              <ChevronRight
                className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-90 text-brand-blue' : 'text-gray-500'}`}
              />
            </button>
            {isOpen && (
              <div className="rb-section-body">
                {section.tldr && (
                  <div className="rb-tldr">
                    <span>TL;DR</span>
                    <p>{section.tldr}</p>
                  </div>
                )}

                <div className="space-y-5">
                  {section.blocks.map((block, index) => (
                    <ReportMarkdown key={`${section.id}-block-${index}`} content={block} />
                  ))}
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
