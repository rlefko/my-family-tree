/**
 * Shared markdown renderer for chat-bubble content. Memoized so frozen turn
 * entries (past assistant content, sealed thinking bursts, subagent traces)
 * skip re-parsing markdown on every stream tick; only the active entry's
 * `content` reference changes per delta.
 */

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-2 hover:underline"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
