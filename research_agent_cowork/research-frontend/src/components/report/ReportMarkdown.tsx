import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

type MarkdownLinkProps = ComponentPropsWithoutRef<'a'> & {
  href?: string;
};

function MarkdownLink({ href, children, ...props }: MarkdownLinkProps) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  );
}

const markdownComponents = {
  a: MarkdownLink,
};

export function ReportMarkdown({ content }: { content: string }) {
  return (
    <div className="markdown-content prose prose-gray max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
