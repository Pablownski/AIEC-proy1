import type { ChatMessage } from "../types/chat";
import { AgentMessage } from "./AgentMessage";
import { TypingIndicator } from "./TypingIndicator";
import { UserMessage } from "./UserMessage";

export interface MessageListProps {
  messages: ChatMessage[];
  agentName: string;
  isAgentTyping: boolean;
  revealingMessageId?: string;
  operation?: number;
  onRevealComplete?: (operation: number) => void;
}

export function MessageList({ messages, agentName, isAgentTyping, revealingMessageId, operation,
  onRevealComplete }: MessageListProps) {
  return (
    <ul className="agichat-message-list" aria-label="Historial de conversación">
      {messages.map((message, index) =>
        message.role === "user" ? (
          <UserMessage key={`${message.id}:${index}`} message={message} />
        ) : (
          <AgentMessage key={`${message.id}:${index}`} message={message}
            revealing={index === messages.length - 1 && message.id === revealingMessageId}
            operation={operation} onRevealComplete={onRevealComplete} />
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
