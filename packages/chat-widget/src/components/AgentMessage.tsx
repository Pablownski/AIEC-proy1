import type { ChatMessage } from "../types/chat";

export interface AgentMessageProps {
  message: ChatMessage;
}

export function AgentMessage({ message }: AgentMessageProps) {
  return (
    <li className="agichat-message agichat-message--agent">
      <p>{message.content}</p>
    </li>
  );
}
