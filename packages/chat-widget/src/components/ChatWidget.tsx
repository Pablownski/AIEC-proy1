import type { ChatTransport } from "../transport/chat-transport";
import { useEffect, useMemo, useState } from "react";
import { ReferenceTabs } from "../actions/reference-tabs";
import type { ExternalAction } from "../types/presentation";
import { TmdbAttribution } from "./TmdbAttribution";
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
  const [fallbacks, setFallbacks] = useState<ExternalAction[]>([]);
  const tabs = useMemo(() => new ReferenceTabs(setFallbacks), []);
  useEffect(() => () => tabs.cancel(), [tabs]);
  const events = useMemo(() => ({ onSend: (text: string) => tabs.reserve(text),
    onReply: (message: import("../types/chat").ChatMessage) => tabs.complete(message),
    onFailure: () => tabs.cancel() }), [tabs]);
  const { messages, status, error, isAgentTyping, sendMessage, retry } = useChat({
    transport,
    welcomeMessage,
    conversationId,
    ...events,
  });

  const isSending = status === "receiving";

  return (
    <section className="agichat-widget" aria-label={`Chat con ${agentName}`}>
      <ChatHeader agentName={agentName} description={description} avatarUrl={avatarUrl} />
      <p className="agichat-capabilities">Asistente de inteligencia artificial: recomiendo películas con TMDB,
        consulto libros y comparo adaptaciones. Al comparar o pedir abrir referencias,
        intento abrir IMDb y Google Books en pestañas nuevas.</p>
      <MessageList messages={messages} agentName={agentName} isAgentTyping={isAgentTyping} />
      {fallbacks.length > 0 && <div className="agichat-reference-fallback" role="status">
        <p>No se pudieron abrir algunas referencias. Ábrelas aquí:</p>
        {fallbacks.map((a) => <a key={a.id} href={a.url} target="_blank" rel="noopener noreferrer">
          Abrir {a.target === "imdb" ? "IMDb" : "Google Books"}
        </a>)}
      </div>}
      {status === "error" && error && (
        <div className="agichat-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={retry}>
            Reintentar
          </button>
        </div>
      )}
      <ChatComposer placeholder={placeholder} disabled={isSending} onSend={sendMessage} />
      <TmdbAttribution />
    </section>
  );
}
