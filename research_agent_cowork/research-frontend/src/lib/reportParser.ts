import {
  ScoreBreakdownItem,
  SourceItem,
  StructuredReport,
  StructuredSection,
  TimelineEvent,
} from '@/types';

interface Heading {
  level: number;
  title: string;
  index: number;
}

function slugify(text: string): string {
  const normalized = text
    .toLowerCase()
    .replace(/[`~!@#$%^&*()+=[\]{};:'",.<>/?\\|]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return normalized || 'section';
}

function countWords(text: string): number {
  const cleaned = text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/[#>*_\-\[\](){}|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) return 0;
  return cleaned.split(' ').length;
}

function extractDomain(url: string): string {
  try {
    const hostname = new URL(url).hostname;
    return hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function toSentenceCase(text: string): string {
  if (!text) return text;
  return text
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeMojibake(text: string): string {
  return text
    // Keep normalization conservative to avoid corrupting normal text.
    .replace(/鈥檚/g, "'s")
    .replace(/檚/g, "'s")
    .replace(/鈥檛/g, "n't")
    .replace(/\uFFFD/g, '');
}

function canonicalHeadingKey(line: string): string {
  return line.replace(/^#{1,6}\s+/, '').trim().toLowerCase();
}

function dedupeAdjacentHeadings(content: string): string {
  const out: string[] = [];
  let prevHeading: { level: number; key: string } | null = null;

  for (const line of content.split('\n')) {
    const m = line.match(/^(#{1,6})\s+(.+?)\s*$/);
    if (!m) {
      out.push(line);
      prevHeading = null;
      continue;
    }

    const level = m[1].length;
    const key = canonicalHeadingKey(line);
    if (prevHeading && prevHeading.level === level && prevHeading.key === key) {
      continue;
    }

    out.push(line);
    prevHeading = { level, key };
  }

  return out.join('\n');
}

export function normalizeReportContent(content: string): string {
  return dedupeAdjacentHeadings(
    normalizeMojibake(content)
      .replace(/\r\n/g, '\n')
      .replace(/^=== REPORT START ===\s*$/gm, '')
      .replace(/^=== REPORT END ===\s*$/gm, '')
      .replace(/^=== END SECTION ===\s*$/gm, '')
      .replace(/^=== SECTION:\s*(.+?)\s*===\s*$/gm, '## $1')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  );
}

function extractMetadata(content: string) {
  const metadata = {
    score: undefined as number | undefined,
    stage: undefined as string | undefined,
    confidence: undefined as string | undefined,
    categories: [] as string[],
  };

  const metaRegex = /^META_(\w+):\s*(.+)$/gm;
  let match: RegExpExecArray | null;
  while ((match = metaRegex.exec(content)) !== null) {
    const key = match[1].toUpperCase();
    const raw = match[2].trim();

    if (key === 'SCORE') {
      const parsed = Number(raw);
      metadata.score = Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : undefined;
      continue;
    }

    if (key === 'STAGE') {
      metadata.stage = raw;
      continue;
    }

    if (key === 'CONFIDENCE') {
      metadata.confidence = raw;
      continue;
    }

    if (key === 'CATEGORIES') {
      try {
        const parsed = JSON.parse(raw);
        metadata.categories = Array.isArray(parsed) ? parsed.map(String) : [];
      } catch {
        metadata.categories = raw
          .replace(/^\[/, '')
          .replace(/\]$/, '')
          .split(',')
          .map((item) => item.trim().replace(/^"|"$/g, ''))
          .filter(Boolean);
      }
    }
  }

  return metadata;
}

function stripSectionNoise(markdown: string, title: string): string {
  const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return markdown
    .replace(new RegExp(`^#{1,6}\\s+${escapedTitle}\\s*$`, 'gim'), '')
    .replace(/^===\s*END SECTION\s*===\s*$/gim, '')
    .replace(/^---\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function extractTldr(markdown: string): string | undefined {
  const tldrMatch = markdown.match(/TL;DR:\s*([\s\S]*?)(?:\n{2,}|\n#{1,6}\s|$)/i);
  if (!tldrMatch) return undefined;
  return tldrMatch[1].replace(/\s+/g, ' ').trim();
}

function extractBlocks(markdown: string): string[] {
  const cleaned = markdown
    .replace(/^\s*TL;DR:\s*[\s\S]*?(?:\n{2,}|\n#{1,6}\s|$)/i, '\n')
    .replace(/^###\s+Scoring Assessment[\s\S]*$/im, '')
    .trim();

  const chunks = cleaned
    .split(/\n{2,}/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .filter((chunk) => !/^#{1,6}\s/.test(chunk));

  return chunks.length > 0 ? chunks : [cleaned].filter(Boolean);
}

function parseHeadings(content: string): Heading[] {
  const regex = /^(#{1,6})\s+(.+?)\s*$/gm;
  const headings: Heading[] = [];
  let match: RegExpExecArray | null;

  while ((match = regex.exec(content)) !== null) {
    headings.push({
      level: match[1].length,
      title: match[2].trim(),
      index: match.index,
    });
  }

  return headings;
}

function normalizeSectionTitle(raw: string): string {
  return raw
    .replace(/^[\d\.\)\-(\[]+\s*/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

const CANONICAL_SECTION_RULES: Array<{ canonical: string; patterns: RegExp[] }> = [
  {
    canonical: 'Project Overview',
    patterns: [/project\s+overview/i, /^overview$/i],
  },
  {
    canonical: 'Technology & Products',
    patterns: [/technology/i, /product/i, /tech stack/i],
  },
  {
    canonical: 'Team & Backers',
    patterns: [/team/i, /backer/i, /founder/i, /investor/i],
  },
  {
    canonical: 'Market & Traction',
    patterns: [/market/i, /traction/i, /growth/i, /business model/i],
  },
  {
    canonical: 'Competitive Landscape',
    patterns: [/competitive/i, /landscape/i, /competition/i],
  },
  {
    canonical: 'Timeline & Milestones',
    patterns: [/timeline/i, /milestone/i],
  },
  {
    canonical: 'Risks & Challenges',
    patterns: [/risk/i, /challenge/i],
  },
  {
    canonical: 'Conclusion & Outlook',
    patterns: [/conclusion/i, /outlook/i, /verdict/i],
  },
];

function canonicalizeSectionTitle(raw: string): string {
  const normalized = normalizeSectionTitle(raw);
  for (const rule of CANONICAL_SECTION_RULES) {
    if (rule.patterns.some((pattern) => pattern.test(normalized))) {
      return rule.canonical;
    }
  }
  return toSentenceCase(normalized);
}

function isIgnoredSectionTitle(title: string): boolean {
  return /^(source index|sources?|meta|information sources|scoring assessment)$/i.test(
    normalizeSectionTitle(title)
  );
}

function selectPrimaryLevel(headings: Heading[]): number {
  const counts = new Map<number, number>();
  for (const heading of headings) {
    if (heading.level > 3) continue;
    counts.set(heading.level, (counts.get(heading.level) || 0) + 1);
  }

  const levels = Array.from(counts.keys()).sort((a, b) => a - b);
  for (const level of levels) {
    if ((counts.get(level) || 0) >= 2) {
      return level;
    }
  }

  return levels[0] ?? 2;
}

function splitSections(content: string): {
  reportTitle: string;
  handle?: string;
  sections: StructuredSection[];
} {
  const headings = parseHeadings(content);
  if (headings.length === 0) {
    return { reportTitle: 'Research Report', sections: [] };
  }

  const reportHeadingIndex = headings.findIndex((heading) => /research report/i.test(heading.title));
  const reportTitle =
    reportHeadingIndex >= 0
      ? headings[reportHeadingIndex].title
      : normalizeSectionTitle(headings[0].title) || 'Research Report';

  const handleMatch = content.match(/@[a-zA-Z0-9_.-]+/);

  const candidates = headings.filter(
    (heading, idx) => idx !== reportHeadingIndex && !isIgnoredSectionTitle(heading.title)
  );
  if (candidates.length === 0) {
    return {
      reportTitle,
      handle: handleMatch?.[0],
      sections: [],
    };
  }

  const primaryLevel = selectPrimaryLevel(candidates);
  const primarySections = candidates.filter((heading) => heading.level === primaryLevel);
  const sectionHeadings = primarySections.length > 0 ? primarySections : candidates;

  const idCounts = new Map<string, number>();
  const sections: StructuredSection[] = [];

  for (let idx = 0; idx < sectionHeadings.length; idx++) {
    const heading = sectionHeadings[idx];
    const nextIndex = idx < sectionHeadings.length - 1 ? sectionHeadings[idx + 1].index : content.length;
    const fullChunk = content.slice(heading.index, nextIndex).trim();
    const chunkWithoutHeading = fullChunk.replace(/^#{1,6}\s+.+\n?/, '').trim();
    const cleaned = stripSectionNoise(chunkWithoutHeading, heading.title);
    if (!cleaned) continue;

    const title = canonicalizeSectionTitle(heading.title);
    const tldr = extractTldr(cleaned);
    const blocks = extractBlocks(cleaned);

    const baseId = slugify(title);
    const seen = idCounts.get(baseId) || 0;
    idCounts.set(baseId, seen + 1);
    const id = seen === 0 ? baseId : `${baseId}-${seen + 1}`;

    sections.push({
      id,
      title,
      tldr,
      blocks,
      markdown: cleaned,
      wordCount: countWords(cleaned),
    });
  }

  return {
    reportTitle,
    handle: handleMatch?.[0],
    sections,
  };
}

const SCORING_RULES = [
  { label: 'Founder Pattern', max: 25 },
  { label: 'Idea Pattern', max: 35 },
  { label: 'Structural Advantage', max: 35 },
  { label: 'Asymmetric Signals', max: 5 },
] as const;

const SCORING_LABEL_ALIASES: Record<string, string> = {
  'Asymmetric Signal': 'Asymmetric Signals',
};

const SCORING_LABELS = [
  'Founder Pattern',
  'Idea Pattern',
  'Structural Advantage',
  'Asymmetric Signals',
  ...Object.keys(SCORING_LABEL_ALIASES),
];

const SCORING_LABEL_PATTERN = SCORING_LABELS.map(escapeRegex).join('|');

function normalizeScoreLabel(label: string): string {
  return SCORING_LABEL_ALIASES[label] ?? label;
}

function finalizeScoring(scoring: ScoreBreakdownItem[], totalScore?: number): ScoreBreakdownItem[] {
  const knownScoring = new Map<string, ScoreBreakdownItem>();
  const extraScoring: ScoreBreakdownItem[] = [];

  for (const item of scoring) {
    const normalizedLabel = normalizeScoreLabel(item.label);
    const normalizedItem = { ...item, label: normalizedLabel };
    if (SCORING_RULES.some((rule) => rule.label === normalizedLabel)) {
      knownScoring.set(normalizedLabel, normalizedItem);
      continue;
    }

    extraScoring.push(normalizedItem);
  }

  if (typeof totalScore === 'number' && Number.isFinite(totalScore)) {
    const missingRules = SCORING_RULES.filter((rule) => !knownScoring.has(rule.label));
    if (missingRules.length === 1) {
      const knownTotal = Array.from(knownScoring.values()).reduce((sum, item) => sum + item.score, 0);
      const inferredScore = totalScore - knownTotal;
      const missingRule = missingRules[0];

      if (inferredScore >= 0 && inferredScore <= missingRule.max) {
        knownScoring.set(missingRule.label, {
          label: missingRule.label,
          score: inferredScore,
          max: missingRule.max,
          percentage: Math.min(100, Math.max(0, (inferredScore / missingRule.max) * 100)),
        });
      }
    }
  }

  return [
    ...SCORING_RULES.map((rule) => knownScoring.get(rule.label)).filter(
      (item): item is ScoreBreakdownItem => Boolean(item)
    ),
    ...extraScoring,
  ];
}

function normalizeScoringContent(content: string): string {
  const scoringHeadingMatch = content.match(/^#{1,6}\s+Scoring Assessment.*$/im);
  const scoringSectionStart = scoringHeadingMatch?.index;
  const prefix = scoringSectionStart === undefined ? '' : content.slice(0, scoringSectionStart);
  const scoringSection = scoringSectionStart === undefined ? content : content.slice(scoringSectionStart);
  const inlineScoreRegex = new RegExp(
    `(^|[^\\n])-\\s*((?:${SCORING_LABEL_PATTERN})\\s*\\(\\d+\\s*\\/\\s*\\d+\\))`,
    'g'
  );

  const normalizedScoringSection = scoringSection
    // Recover score bullets that were merged into the previous paragraph or a broken link.
    .replace(inlineScoreRegex, '$1\n- $2')
    .replace(/\n{3,}/g, '\n\n');

  return `${prefix}${normalizedScoringSection}`;
}

function extractScoring(content: string, totalScore?: number): ScoreBreakdownItem[] {
  const scoring: ScoreBreakdownItem[] = [];
  const scoringContent = normalizeScoringContent(content);
  const scoreRegex = /^-\s*([^(\n]+?)\s*\((\d+)\s*\/\s*(\d+)\)/gm;
  let match: RegExpExecArray | null;

  while ((match = scoreRegex.exec(scoringContent)) !== null) {
    const score = Number(match[2]);
    const max = Number(match[3]);
    if (!Number.isFinite(score) || !Number.isFinite(max) || max <= 0) continue;

    scoring.push({
      label: match[1].trim(),
      score,
      max,
      percentage: Math.min(100, Math.max(0, (score / max) * 100)),
    });
  }

  return finalizeScoring(scoring, totalScore);
}

function deriveTimelineCategory(text: string): TimelineEvent['category'] {
  const lowered = text.toLowerCase();
  if (
    lowered.includes('launch') ||
    lowered.includes('beta') ||
    lowered.includes('update') ||
    lowered.includes('support')
  ) {
    return 'product';
  }
  if (
    lowered.includes('announces') ||
    lowered.includes('report') ||
    lowered.includes('manifesto')
  ) {
    return 'announcement';
  }
  if (lowered.includes('created') || lowered.includes('commit') || lowered.includes('milestone')) {
    return 'milestone';
  }
  return 'unknown';
}

function extractTimeline(sections: StructuredSection[]): TimelineEvent[] {
  const timelineSection = sections.find((section) => /timeline|milestone/i.test(section.title));
  if (!timelineSection) return [];

  const events: TimelineEvent[] = [];
  const bulletRegex = /^\s*-\s*(?:\*\*)?(.+?)(?:\*\*)?\s*(?:[:：]|[-–—])\s*(.+)$/gm;
  let match: RegExpExecArray | null;

  while ((match = bulletRegex.exec(timelineSection.markdown)) !== null) {
    const date = match[1].trim();
    const event = match[2].trim();
    if (!date || !event) continue;
    events.push({
      date,
      event,
      category: deriveTimelineCategory(event),
    });
  }

  return events;
}

function extractSourceLinesFromIndex(content: string): SourceItem[] {
  const sourceItems: SourceItem[] = [];
  const sourceIndexRegex = /^S(\d+)\s+(https?:\/\/\S+)/gm;
  let match: RegExpExecArray | null;

  while ((match = sourceIndexRegex.exec(content)) !== null) {
    const id = `S${match[1]}`;
    const url = match[2].trim();
    sourceItems.push({
      id,
      label: id,
      url,
      domain: extractDomain(url),
    });
  }

  return sourceItems;
}

function extractSources(content: string): SourceItem[] {
  const fromIndex = extractSourceLinesFromIndex(content);
  if (fromIndex.length > 0) return fromIndex;

  const sourceMap = new Map<string, SourceItem>();

  const markdownLinkRegex = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let match: RegExpExecArray | null;
  while ((match = markdownLinkRegex.exec(content)) !== null) {
    const label = match[1].trim();
    const url = match[2].trim();
    if (sourceMap.has(url)) continue;
    const id = `S${sourceMap.size + 1}`;
    sourceMap.set(url, {
      id,
      label: /^https?:\/\//.test(label) ? extractDomain(label) : label,
      url,
      domain: extractDomain(url),
    });
  }

  const bareUrlRegex = /(^|[\s(])(https?:\/\/[^\s)]+)/g;
  while ((match = bareUrlRegex.exec(content)) !== null) {
    const url = match[2].trim();
    if (sourceMap.has(url)) continue;
    const id = `S${sourceMap.size + 1}`;
    sourceMap.set(url, {
      id,
      label: id,
      url,
      domain: extractDomain(url),
    });
  }

  return Array.from(sourceMap.values());
}

export function parseStructuredReport(rawContent: string): StructuredReport {
  const normalizedContent = normalizeReportContent(rawContent);
  const metadata = extractMetadata(normalizedContent);
  const { reportTitle, handle, sections } = splitSections(normalizedContent);
  const sources = extractSources(normalizedContent);
  const scoring = extractScoring(normalizedContent, metadata.score);
  const timeline = extractTimeline(sections);
  const totalWords = countWords(normalizedContent);

  return {
    title: reportTitle,
    handle,
    normalizedContent,
    metadata,
    sections,
    scoring,
    timeline,
    sources,
    totalWords,
    readingMinutes: Math.max(1, Math.round(totalWords / 220)),
  };
}
