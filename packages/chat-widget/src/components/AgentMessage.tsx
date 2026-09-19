import type { ChatMessage } from "../types/chat";
import { MarkdownRenderer } from "./MarkdownRenderer";

export interface AgentMessageProps {
  message: ChatMessage;
}

export function AgentMessage({ message }: AgentMessageProps) {
  return (
    <li className="agichat-message agichat-message--agent">
      <MarkdownRenderer content={message.content} />
    </li>
  );
}
