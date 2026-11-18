import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWidget } from "../src/components/ChatWidget";
import { HttpChatTransport } from "../src/transport/http-transport";
import { WebSocketChatTransport, type WebSocketLike } from "../src/transport/websocket-transport";
import { ChatTransportError } from "../src/transport/chat-transport";
import { richReply, wireReply } from "./presentation-fixture";
import { mockMotion } from "./motion-fixture";
import type { ChatMessage } from "../src/types/chat";

beforeEach(() => { vi.useFakeTimers(); mockMotion(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const avatar = () => screen.getByRole("img", { name: /^Damián:/ });
function send(text = "Hola") {
  fireEvent.change(screen.getByLabelText("Escribe un mensaje"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar mensaje" }));
}
async function flush() { await act(async () => { await Promise.resolve(); }); }

function controller(kind: "HTTP" | "WebSocket") {
  if (kind === "HTTP") {
    let resolve!: (value: Response) => void;
    const pending = new Promise<Response>((r) => { resolve = r; });
    vi.stubGlobal("fetch", vi.fn(() => pending));
    return { transport: new HttpChatTransport({ baseUrl: "http://api.test" }),
      reply: () => resolve({ ok: true, json: async () => wireReply } as Response),
      fail: () => resolve({ ok: false, status: 503 } as Response) };
  }
  const listeners: Record<string, Set<(event: unknown) => void>> = {};
  const socket: WebSocketLike = {
    readyState: 1, send: vi.fn(), close: vi.fn(),
    addEventListener: (type, fn) => { (listeners[type] ??= new Set()).add(fn); },
    removeEventListener: (type, fn) => { listeners[type]?.delete(fn); },
  };
  const emit = (payload: unknown) => [...(listeners.message ?? [])].forEach((fn) => fn({ data: JSON.stringify(payload) }));
  return { transport: new WebSocketChatTransport({ url: "ws://api.test", createWebSocket: () => socket }),
    reply: () => {
      emit({ type: "agent_start" });
      emit({ type: "agent_message", message: wireReply.message });
      emit({ type: "agent_end" });
    },
    fail: () => emit({ type: "error", detail: "Servicio no disponible" }),
  };
}

describe("avatar with actual HTTP/WebSocket transports and mocked I/O", () => {
  it.each(["HTTP", "WebSocket"] as const)("%s: idle → thinking → talking → done → idle preserves cards", async (kind) => {
    const io = controller(kind);
    render(<ChatWidget agentName="Damián" transport={io.transport} />);
    expect(avatar()).toHaveAttribute("data-state", "idle");
    send(); await flush();
    expect(avatar()).toHaveAttribute("data-state", "thinking");
    act(() => vi.advanceTimersByTime(400));
    expect(avatar().querySelector("img")?.getAttribute("src")).toContain("think_3.png");
    await act(async () => io.reply());
    expect(avatar()).toHaveAttribute("data-state", "talking");
    expect(screen.queryByLabelText("Comparación libro y película")).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(180));
    expect(avatar().querySelector("img")?.getAttribute("src")).toContain("talk_2.png");
    act(() => vi.advanceTimersByTime(6000));
    expect(avatar()).toHaveAttribute("data-state", "done");
    expect(screen.getByLabelText("Comparación libro y película")).toBeVisible();
    expect(screen.getByAltText("Póster de Obra de prueba")).toBeVisible();
    act(() => vi.advanceTimersByTime(2999));
    expect(avatar()).toHaveAttribute("data-state", "done");
    act(() => vi.advanceTimersByTime(1));
    expect(avatar()).toHaveAttribute("data-state", "idle");
  });

  it.each(["HTTP", "WebSocket"] as const)("%s: rejected request shows error for 3000 ms", async (kind) => {
    const io = controller(kind);
    render(<ChatWidget agentName="Damián" transport={io.transport} />);
    send(); await flush();
    await act(async () => io.fail());
    expect(avatar()).toHaveAttribute("data-state", "error");
    expect(screen.getByRole("alert")).toBeVisible();
    act(() => vi.advanceTimersByTime(2999));
    expect(avatar()).toHaveAttribute("data-state", "error");
    act(() => vi.advanceTimersByTime(1));
    expect(avatar()).toHaveAttribute("data-state", "idle");
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeEnabled();
  });

  it.each(["done", "error"] as const)("new request interrupts %s; duplicate reply IDs animate only the latest message", async (terminal) => {
    let resolve!: (message: ChatMessage) => void;
    const pending = new Promise<ChatMessage>((r) => { resolve = r; });
    const transport = { sendMessage: vi.fn()
      .mockImplementationOnce(() => terminal === "done" ? Promise.resolve(richReply) : Promise.reject(new ChatTransportError("No disponible")))
      .mockReturnValueOnce(pending) };
    const { container, unmount } = render(<ChatWidget agentName="Damián" transport={transport} />);
    send(); await flush();
    if (terminal === "done") act(() => vi.advanceTimersByTime(6000));
    expect(avatar()).toHaveAttribute("data-state", terminal);
    act(() => vi.advanceTimersByTime(2000));
    send("Otra pregunta");
    expect(avatar()).toHaveAttribute("data-state", "thinking");
    act(() => vi.advanceTimersByTime(1000));
    expect(avatar()).toHaveAttribute("data-state", "thinking");
    await act(async () => resolve(richReply));
    expect(avatar()).toHaveAttribute("data-state", "talking");
    expect(container.querySelectorAll(".agichat-message-preview")).toHaveLength(1);
    act(() => vi.advanceTimersByTime(6000));
    expect(avatar()).toHaveAttribute("data-state", "done");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("new operation stops unfinished reveal and cleans timers on unmount", async () => {
    const transport = { sendMessage: vi.fn().mockResolvedValueOnce(richReply)
      .mockReturnValueOnce(new Promise(() => {})) };
    const { container, unmount } = render(<ChatWidget agentName="Damián" transport={transport} />);
    send(); await flush();
    expect(avatar()).toHaveAttribute("data-state", "talking");
    act(() => vi.advanceTimersByTime(60));
    send("Nueva consulta");
    act(() => vi.advanceTimersByTime(6000));
    expect(avatar()).toHaveAttribute("data-state", "thinking");
    expect(container.querySelector(".agichat-message-preview")).toBeNull();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("fast reply with reduced motion shows formatted text and cards immediately", async () => {
    mockMotion(true);
    const transport = { sendMessage: vi.fn().mockResolvedValue(richReply) };
    const { container } = render(<ChatWidget agentName="Damián" transport={transport} />);
    send(); await flush();
    expect(avatar()).toHaveAttribute("data-state", "done");
    expect(container.querySelector(".agichat-message-preview")).toBeNull();
    expect(screen.getByLabelText("Comparación libro y película")).toBeVisible();
    expect(screen.getByText(richReply.content)).toBeVisible();
  });

  it("changing transport cancels presentation and ignores its late reply", async () => {
    let resolve!: (message: ChatMessage) => void;
    const first = { sendMessage: vi.fn(() => new Promise<ChatMessage>((r) => { resolve = r; })) };
    const { rerender } = render(<ChatWidget agentName="Damián" transport={first} />);
    send();
    rerender(<ChatWidget agentName="Damián" transport={{ sendMessage: vi.fn() }} />);
    expect(avatar()).toHaveAttribute("data-state", "idle");
    await act(async () => resolve(richReply));
    expect(screen.queryByText(richReply.content)).not.toBeInTheDocument();
    expect(avatar()).toHaveAttribute("data-state", "idle");
  });
});
