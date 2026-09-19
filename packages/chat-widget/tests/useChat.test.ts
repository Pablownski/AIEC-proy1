import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatTransportError } from "../src/transport/chat-transport";
import { useChat } from "../src/hooks/useChat";
import type { ChatMessage, ChatTransport } from "../src/index";

function makeTransport(impl: ChatTransport["sendMessage"]): ChatTransport {
  return { sendMessage: impl };
}

describe("useChat", () => {
  it("seeds the conversation with a welcome message", () => {
    const { result } = renderHook(() =>
      useChat({ transport: makeTransport(vi.fn()), welcomeMessage: "¡Hola!" }),
    );

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]!.role).toBe("assistant");
    expect(result.current.messages[0]!.content).toBe("¡Hola!");
  });

  it("starts idle with no messages when no welcome message is configured", () => {
    const { result } = renderHook(() => useChat({ transport: makeTransport(vi.fn()) }));

    expect(result.current.messages).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("appends the user message immediately and the agent reply once resolved", async () => {
    const reply: ChatMessage = {
      id: "2",
      role: "assistant",
      content: "hola de vuelta",
      createdAt: "2026-01-01T00:00:01.000Z",
    };
    const { result } = renderHook(() =>
      useChat({ transport: makeTransport(async () => reply) }),
    );

    act(() => result.current.sendMessage("Hola"));

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]!.role).toBe("user");

    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    expect(result.current.messages[1]).toEqual(reply);
    expect(result.current.status).toBe("idle");
  });

  it("ignores empty or whitespace-only messages", () => {
    const send = vi.fn();
    const { result } = renderHook(() => useChat({ transport: makeTransport(send) }));

    act(() => result.current.sendMessage("   "));

    expect(send).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });

  it("sets status to error and exposes a safe message on transport failure", async () => {
    const { result } = renderHook(() =>
      useChat({
        transport: makeTransport(async () => {
          throw new ChatTransportError("Backend no disponible");
        }),
      }),
    );

    act(() => result.current.sendMessage("Hola"));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Backend no disponible");
  });

  it("falls back to a generic error message for unexpected exceptions", async () => {
    const { result } = renderHook(() =>
      useChat({
        transport: makeTransport(async () => {
          throw new Error("boom");
        }),
      }),
    );

    act(() => result.current.sendMessage("Hola"));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("No pudimos enviar tu mensaje. Intenta nuevamente.");
  });

  it("retries the last failed message without duplicating the user bubble", async () => {
    let attempts = 0;
    const reply: ChatMessage = {
      id: "2",
      role: "assistant",
      content: "ok",
      createdAt: "2026-01-01T00:00:01.000Z",
    };
    const { result } = renderHook(() =>
      useChat({
        transport: makeTransport(async () => {
          attempts += 1;
          if (attempts === 1) throw new ChatTransportError("falló");
          return reply;
        }),
      }),
    );

    act(() => result.current.sendMessage("Hola"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.messages).toHaveLength(1);

    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("idle"));

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
  });

  it("reports isAgentTyping while the transport call is pending", async () => {
    let resolve!: (message: ChatMessage) => void;
    const pending = new Promise<ChatMessage>((r) => {
      resolve = r;
    });
    const { result } = renderHook(() => useChat({ transport: makeTransport(() => pending) }));

    act(() => result.current.sendMessage("Hola"));
    expect(result.current.isAgentTyping).toBe(true);

    await act(async () => {
      resolve({ id: "2", role: "assistant", content: "ok", createdAt: "2026-01-01T00:00:01.000Z" });
      await pending;
    });

    expect(result.current.isAgentTyping).toBe(false);
  });
});
