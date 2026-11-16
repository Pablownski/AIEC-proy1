import type { ChatTransport } from "./chat-transport";
import { ChatTransportError } from "./chat-transport";
import type { ChatMessage } from "../types/chat";
import { decodeMessage } from "./decode-message";

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
        let payload: Record<string, unknown>;
        try { payload = JSON.parse(raw) as Record<string, unknown>;
          if (!payload || typeof payload !== "object") throw new Error();
        } catch { cleanup(); reject(new ChatTransportError("Evento del servidor inválido.")); return; }

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
          try { pendingReply = decodeMessage(payload.message); }
          catch (error) { cleanup(); reject(error); }
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
