import type { ChatMessage } from "../types/chat";

export interface UserMessageProps {
  message: ChatMessage;
}

export function UserMessage({ message }: UserMessageProps) {
  return (
    <li className="agichat-message agichat-message--user">
      <p>{message.content}</p>
    </li>
  );
}
