import type { ChatTransport } from "./chat-transport";
import { ChatTransportError } from "./chat-transport";
import type { ChatMessage } from "../types/chat";

export interface HttpChatTransportOptions {
  baseUrl: string;
  timeoutMs?: number;
}

interface BackendChatMessage {
  id: string;
  role: ChatMessage["role"];
  content: string;
  created_at: string;
}

interface BackendChatResponse {
  conversation_id: string;
  message: BackendChatMessage;
}

function isBackendChatResponse(value: unknown): value is BackendChatResponse {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.conversation_id !== "string") return false;
  const message = candidate.message as Record<string, unknown> | undefined;
  return (
    typeof message === "object" &&
    message !== null &&
    typeof message.id === "string" &&
    typeof message.role === "string" &&
    typeof message.content === "string" &&
    typeof message.created_at === "string"
  );
}

/** Talks to the FastAPI REST endpoint (POST /api/v1/chat). */
export class HttpChatTransport implements ChatTransport {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: HttpChatTransportOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 15000;
  }

  async sendMessage(conversationId: string, message: ChatMessage): Promise<ChatMessage> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: { role: message.role, content: message.content },
        }),
        signal: controller.signal,
      });
    } catch (error) {
      throw new ChatTransportError("No pudimos enviar tu mensaje. Intenta nuevamente.", error);
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      throw new ChatTransportError(
        `El servidor respondió con un error (${response.status}).`,
      );
    }

    const body: unknown = await response.json();
    if (!isBackendChatResponse(body)) {
      throw new ChatTransportError("La respuesta del servidor no tiene el formato esperado.");
    }

    return {
      id: body.message.id,
      role: body.message.role,
      content: body.message.content,
      createdAt: body.message.created_at,
    };
  }
}
