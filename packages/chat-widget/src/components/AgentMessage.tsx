import type { ChatMessage } from "../types/chat";
import { RevealedMarkdown } from "./RevealedMarkdown";
import { CatalogCards } from "./CatalogCards";

export interface AgentMessageProps {
  message: ChatMessage;
  revealing?: boolean;
  operation?: number;
  onRevealComplete?: (operation: number) => void;
}

export function AgentMessage({ message, revealing = false, operation = 0, onRevealComplete }: AgentMessageProps) {
  return (
    <li className="agichat-message agichat-message--agent">
      <RevealedMarkdown content={message.content} revealing={revealing} operation={operation}
        onComplete={onRevealComplete} />
      {!revealing && message.metadata && <CatalogCards data={message.metadata} />}
    </li>
  );
}
