import type { ChatMessage } from "../types/chat";
import { AgentMessage } from "./AgentMessage";
import { TypingIndicator } from "./TypingIndicator";
import { UserMessage } from "./UserMessage";

export interface MessageListProps {
  messages: ChatMessage[];
  agentName: string;
  isAgentTyping: boolean;
}

export function MessageList({ messages, agentName, isAgentTyping }: MessageListProps) {
  return (
    <ul className="agichat-message-list" aria-label="Historial de conversación">
      {messages.map((message) =>
        message.role === "user" ? (
          <UserMessage key={message.id} message={message} />
        ) : (
          <AgentMessage key={message.id} message={message} />
        ),
      )}
      {isAgentTyping && (
        <li className="agichat-message agichat-message--agent">
          <TypingIndicator agentName={agentName} />
        </li>
      )}
    </ul>
  );
}
