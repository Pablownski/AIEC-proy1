import { describe, expect, it, vi } from "vitest";
import { ChatTransportError } from "../src/transport/chat-transport";
import { WebSocketChatTransport, type WebSocketLike } from "../src/transport/websocket-transport";
import type { ChatMessage } from "../src/types/chat";

const userMessage: ChatMessage = {
  id: "1",
  role: "user",
  content: "Hola",
  createdAt: "2026-01-01T00:00:00.000Z",
};

/** Lets the microtask queue drain so the transport's async continuations run. */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

class FakeWebSocket implements WebSocketLike {
  static OPEN = 1;
  readyState = 0;
  sent: string[] = [];
  private listeners: Record<string, Array<(event: unknown) => void>> = {};

  addEventListener(type: string, listener: (event: unknown) => void): void {
    (this.listeners[type] ??= []).push(listener);
  }

  removeEventListener(type: string, listener: (event: unknown) => void): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== listener);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.emit("close", {});
  }

  emit(type: string, event: unknown): void {
    for (const listener of this.listeners[type] ?? []) listener(event);
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.emit("open", {});
  }

  message(payload: unknown): void {
    this.emit("message", { data: JSON.stringify(payload) });
  }
}

function setup(onTypingChange?: (isTyping: boolean) => void) {
  const socket = new FakeWebSocket();
  const transport = new WebSocketChatTransport({
    url: "ws://api.local/ws/chat",
    createWebSocket: () => socket,
    onTypingChange,
  });
  return { socket, transport };
}

describe("WebSocketChatTransport", () => {
  it("connects lazily and sends the message once open", async () => {
    const { socket, transport } = setup();

    const pending = transport.sendMessage("conv-1", userMessage);
    socket.open();
    await flush();
    socket.message({ type: "agent_start" });
    socket.message({
      type: "agent_message",
      conversation_id: "conv-1",
      message: {
        id: "2",
        role: "assistant",
        content: "Hola de vuelta",
        created_at: "2026-01-01T00:00:01.000Z",
      },
    });
    socket.message({ type: "agent_end" });

    const reply = await pending;

    expect(JSON.parse(socket.sent[0]!)).toEqual({ conversation_id: "conv-1", content: "Hola" });
    expect(reply).toEqual({
      id: "2",
      role: "assistant",
      content: "Hola de vuelta",
      createdAt: "2026-01-01T00:00:01.000Z",
    });
  });

  it("reports typing state via agent_start/agent_end", async () => {
    const onTypingChange = vi.fn();
    const { socket, transport } = setup(onTypingChange);

    const pending = transport.sendMessage("conv-1", userMessage);
    socket.open();
    await flush();
    socket.message({ type: "agent_start" });
    socket.message({
      type: "agent_message",
      conversation_id: "conv-1",
      message: {
        id: "2",
        role: "assistant",
        content: "ok",
        created_at: "2026-01-01T00:00:01.000Z",
      },
    });
    socket.message({ type: "agent_end" });
    await pending;

    expect(onTypingChange).toHaveBeenNthCalledWith(1, true);
    expect(onTypingChange).toHaveBeenNthCalledWith(2, false);
  });

  it("rejects with a ChatTransportError when the server sends an error event", async () => {
    const { socket, transport } = setup();

    const pending = transport.sendMessage("conv-1", userMessage);
    socket.open();
    await flush();
    socket.message({ type: "agent_start" });
    socket.message({ type: "error", detail: "No pudimos enviar tu mensaje. Intenta nuevamente." });

    await expect(pending).rejects.toBeInstanceOf(ChatTransportError);
  });

  it("rejects with a ChatTransportError when the socket errors before opening", async () => {
    const { socket, transport } = setup();

    const pending = transport.sendMessage("conv-1", userMessage);
    socket.emit("error", {});

    await expect(pending).rejects.toBeInstanceOf(ChatTransportError);
  });

  it("rejects with a ChatTransportError if the connection closes mid-flight", async () => {
    const { socket, transport } = setup();

    const pending = transport.sendMessage("conv-1", userMessage);
    socket.open();
    await flush();
    socket.message({ type: "agent_start" });
    socket.close();

    await expect(pending).rejects.toBeInstanceOf(ChatTransportError);
  });

  it("reuses the same socket connection across multiple messages", async () => {
    let created = 0;
    const socket = new FakeWebSocket();
    const transport = new WebSocketChatTransport({
      url: "ws://api.local/ws/chat",
      createWebSocket: () => {
        created += 1;
        return socket;
      },
    });

    const first = transport.sendMessage("conv-1", userMessage);
    socket.open();
    await flush();
    socket.message({ type: "agent_start" });
    socket.message({
      type: "agent_message",
      conversation_id: "conv-1",
      message: { id: "2", role: "assistant", content: "a", created_at: "2026-01-01T00:00:01.000Z" },
    });
    socket.message({ type: "agent_end" });
    await first;

    const second = transport.sendMessage("conv-1", userMessage);
    await flush();
    socket.message({ type: "agent_start" });
    socket.message({
      type: "agent_message",
      conversation_id: "conv-1",
      message: { id: "3", role: "assistant", content: "b", created_at: "2026-01-01T00:00:02.000Z" },
    });
    socket.message({ type: "agent_end" });
    await second;

    expect(created).toBe(1);
  });
});
