import type { ChatMessage } from "../types/chat";

/**
 * Transport-agnostic contract between ChatWidget and the backend.
 * ChatWidget must never call fetch()/WebSocket directly — only through this.
 */
export interface ChatTransport {
  sendMessage(conversationId: string, message: ChatMessage): Promise<ChatMessage>;
}

export class ChatTransportError extends Error {
  constructor(
    message: string,
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ChatTransportError";
  }
}
