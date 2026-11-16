import { useCallback, useRef, useState } from "react";
import { ChatTransportError, type ChatTransport } from "../transport/chat-transport";
import type { ChatMessage, ChatStatus } from "../types/chat";
import { createId } from "./createId";

const GENERIC_ERROR = "No pudimos enviar tu mensaje. Intenta nuevamente.";

export interface UseChatOptions {
  transport: ChatTransport;
  welcomeMessage?: string;
  conversationId?: string;
  onSend?: (content: string) => void;
  onReply?: (message: ChatMessage) => void;
  onFailure?: () => void;
}

export interface UseChatResult {
  messages: ChatMessage[];
  status: ChatStatus;
  error: string | null;
  isAgentTyping: boolean;
  sendMessage: (content: string) => void;
  retry: () => void;
}

function buildWelcomeMessage(content: string): ChatMessage {
  return {
    id: createId(),
    role: "assistant",
    content,
    createdAt: new Date().toISOString(),
  };
}

export function useChat({ transport, welcomeMessage, conversationId, onSend, onReply, onFailure }: UseChatOptions): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    welcomeMessage ? [buildWelcomeMessage(welcomeMessage)] : [],
  );
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const conversationIdRef = useRef(conversationId ?? createId());
  const lastFailedMessageRef = useRef<ChatMessage | null>(null);

  const attemptSend = useCallback(
    async (userMessage: ChatMessage) => {
      setStatus("receiving");
      setError(null);
      try {
        const reply = await transport.sendMessage(conversationIdRef.current, userMessage);
        setMessages((prev) => [...prev, reply]);
        setStatus("idle");
        lastFailedMessageRef.current = null;
        onReply?.(reply);
      } catch (err) {
        setStatus("error");
        setError(err instanceof ChatTransportError ? err.message : GENERIC_ERROR);
        lastFailedMessageRef.current = userMessage;
        onFailure?.();
      }
    },
    [transport, onReply, onFailure],
  );

  const sendMessage = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;
      onSend?.(trimmed);
      const userMessage: ChatMessage = {
        id: createId(),
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
      void attemptSend(userMessage);
    },
    [attemptSend, onSend],
  );

  const retry = useCallback(() => {
    const failed = lastFailedMessageRef.current;
    if (failed) { onSend?.(failed.content); void attemptSend(failed); }
  }, [attemptSend, onSend]);

  return {
    messages,
    status,
    error,
    isAgentTyping: status === "receiving",
    sendMessage,
    retry,
  };
}
