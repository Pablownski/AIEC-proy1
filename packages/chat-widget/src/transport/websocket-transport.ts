import type { ChatTransport } from "./chat-transport";
import { ChatTransportError } from "./chat-transport";
import type { ChatMessage } from "../types/chat";

export interface WebSocketLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  addEventListener(type: string, listener: (event: unknown) => void): void;
  removeEventListener(type: string, listener: (event: unknown) => void): void;
}

const OPEN_STATE = 1;

export interface WebSocketChatTransportOptions {
  url: string;
  createWebSocket?: (url: string) => WebSocketLike;
  onTypingChange?: (isTyping: boolean) => void;
}

/** Talks to the FastAPI WebSocket endpoint (/ws/chat), reusing one connection. */
export class WebSocketChatTransport implements ChatTransport {
  private readonly url: string;
  private readonly createWebSocket: (url: string) => WebSocketLike;
  private readonly onTypingChange?: (isTyping: boolean) => void;
  private socket: WebSocketLike | undefined;
  private connectPromise: Promise<WebSocketLike> | undefined;

  constructor(options: WebSocketChatTransportOptions) {
    this.url = options.url;
    this.createWebSocket =
      options.createWebSocket ?? ((url) => new WebSocket(url) as unknown as WebSocketLike);
    this.onTypingChange = options.onTypingChange;
  }

  private connect(): Promise<WebSocketLike> {
    if (this.socket && this.socket.readyState === OPEN_STATE) {
      return Promise.resolve(this.socket);
    }
    if (this.connectPromise) return this.connectPromise;

    const socket = this.createWebSocket(this.url);
    this.socket = socket;

    this.connectPromise = new Promise<WebSocketLike>((resolve, reject) => {
      if (socket.readyState === OPEN_STATE) {
        resolve(socket);
        return;
      }
      const onOpen = () => {
        cleanup();
        resolve(socket);
      };
      const onError = () => {
        cleanup();
        this.connectPromise = undefined;
        reject(new ChatTransportError("No pudimos conectar con el servidor."));
      };
      const cleanup = () => {
        socket.removeEventListener("open", onOpen);
        socket.removeEventListener("error", onError);
      };
      socket.addEventListener("open", onOpen);
      socket.addEventListener("error", onError);
    });

    return this.connectPromise;
  }

  async sendMessage(conversationId: string, message: ChatMessage): Promise<ChatMessage> {
    const socket = await this.connect();

    return new Promise<ChatMessage>((resolve, reject) => {
      let pendingReply: ChatMessage | undefined;

      const onMessage = (event: unknown) => {
        const raw = (event as { data: string }).data;
        const payload = JSON.parse(raw) as Record<string, unknown>;

        if (payload.type === "agent_start") {
          this.onTypingChange?.(true);
          return;
        }
        if (payload.type === "agent_end") {
          this.onTypingChange?.(false);
          if (pendingReply) {
            cleanup();
            resolve(pendingReply);
          }
          return;
        }
        if (payload.type === "error") {
          cleanup();
          reject(
            new ChatTransportError(
              typeof payload.detail === "string"
                ? payload.detail
                : "No pudimos enviar tu mensaje. Intenta nuevamente.",
            ),
          );
          return;
        }
        if (payload.type === "agent_message") {
          const backendMessage = payload.message as {
            id: string;
            role: ChatMessage["role"];
            content: string;
            created_at: string;
          };
          pendingReply = {
            id: backendMessage.id,
            role: backendMessage.role,
            content: backendMessage.content,
            createdAt: backendMessage.created_at,
          };
        }
      };

      const onClose = () => {
        cleanup();
        reject(new ChatTransportError("La conexión se cerró antes de recibir una respuesta."));
      };

      const cleanup = () => {
        socket.removeEventListener("message", onMessage);
        socket.removeEventListener("close", onClose);
      };

      socket.addEventListener("message", onMessage);
      socket.addEventListener("close", onClose);

      socket.send(JSON.stringify({ conversation_id: conversationId, content: message.content }));
    });
  }
}
