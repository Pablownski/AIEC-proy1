import type { ChatMessage } from "../types/chat";
import { parseMetadata } from "../types/presentation";
import { ChatTransportError } from "./chat-transport";

export function decodeMessage(value: unknown): ChatMessage {
  try {
    if (!value || typeof value !== "object") throw new Error();
    const m = value as Record<string, unknown>;
    if (typeof m.id !== "string" || !["user", "assistant", "system"].includes(String(m.role)) ||
        typeof m.content !== "string" || typeof m.created_at !== "string") throw new Error();
    const metadata = parseMetadata(m.metadata);
    return { id: m.id, role: m.role as ChatMessage["role"], content: m.content,
      createdAt: m.created_at, ...(metadata ? { metadata } : {}) };
  } catch {
    throw new ChatTransportError("La respuesta del servidor no tiene el formato esperado.");
  }
}
