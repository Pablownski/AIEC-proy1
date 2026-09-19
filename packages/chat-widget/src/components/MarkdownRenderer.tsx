import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

export interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders assistant messages as sanitized Markdown.
 * Never uses dangerouslySetInnerHTML — rehype-sanitize strips unsafe nodes
 * (script tags, event handlers, javascript: URLs) before anything reaches the DOM.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="agichat-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
