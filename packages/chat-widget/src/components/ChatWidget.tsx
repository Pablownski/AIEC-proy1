import type { ChatTransport } from "../transport/chat-transport";
import type { ChatWidgetConfig } from "../types/chat";
import { useChat } from "../hooks/useChat";
import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";

export interface ChatWidgetProps extends ChatWidgetConfig {
  transport: ChatTransport;
  conversationId?: string;
}

export function ChatWidget({
  agentName,
  description,
  avatarUrl,
  placeholder,
  welcomeMessage,
  transport,
  conversationId,
}: ChatWidgetProps) {
  const { messages, status, error, isAgentTyping, sendMessage, retry } = useChat({
    transport,
    welcomeMessage,
    conversationId,
  });

  const isSending = status === "receiving";

  return (
    <section className="agichat-widget" aria-label={`Chat con ${agentName}`}>
      <ChatHeader agentName={agentName} description={description} avatarUrl={avatarUrl} />
      <MessageList messages={messages} agentName={agentName} isAgentTyping={isAgentTyping} />
      {status === "error" && error && (
        <div className="agichat-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={retry}>
            Reintentar
          </button>
        </div>
      )}
      <ChatComposer placeholder={placeholder} disabled={isSending} onSend={sendMessage} />
    </section>
  );
}
