import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatTransportError } from "../src/transport/chat-transport";
import { HttpChatTransport } from "../src/transport/http-transport";
import type { ChatMessage } from "../src/types/chat";

const userMessage: ChatMessage = {
  id: "1",
  role: "user",
  content: "Hola",
  createdAt: "2026-01-01T00:00:00.000Z",
};

function mockFetchOnce(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
    ...response,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("HttpChatTransport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the request to the configured baseUrl with the right payload", async () => {
    const fetchMock = mockFetchOnce({
      json: async () => ({
        conversation_id: "conv-1",
        message: {
          id: "2",
          role: "assistant",
          content: "Hola de vuelta",
          created_at: "2026-01-01T00:00:01.000Z",
        },
      }),
    });
    const transport = new HttpChatTransport({ baseUrl: "http://api.local" });

    await transport.sendMessage("conv-1", userMessage);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.local/api/v1/chat",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          conversation_id: "conv-1",
          message: { role: "user", content: "Hola" },
        }),
      }),
    );
  });

  it("maps the backend response into a ChatMessage", async () => {
    mockFetchOnce({
      json: async () => ({
        conversation_id: "conv-1",
        message: {
          id: "2",
          role: "assistant",
          content: "Hola de vuelta",
          created_at: "2026-01-01T00:00:01.000Z",
        },
      }),
    });
    const transport = new HttpChatTransport({ baseUrl: "http://api.local" });

    const reply = await transport.sendMessage("conv-1", userMessage);

    expect(reply).toEqual({
      id: "2",
      role: "assistant",
      content: "Hola de vuelta",
      createdAt: "2026-01-01T00:00:01.000Z",
    });
  });

  it("throws a ChatTransportError on a non-ok HTTP response", async () => {
    mockFetchOnce({ ok: false, status: 500 });
    const transport = new HttpChatTransport({ baseUrl: "http://api.local" });

    await expect(transport.sendMessage("conv-1", userMessage)).rejects.toBeInstanceOf(
      ChatTransportError,
    );
  });

  it("throws a ChatTransportError when fetch rejects (network error)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    const transport = new HttpChatTransport({ baseUrl: "http://api.local" });

    await expect(transport.sendMessage("conv-1", userMessage)).rejects.toBeInstanceOf(
      ChatTransportError,
    );
  });

  it("throws a ChatTransportError when the response body is malformed", async () => {
    mockFetchOnce({
      json: async () => ({ unexpected: true }),
    });
    const transport = new HttpChatTransport({ baseUrl: "http://api.local" });

    await expect(transport.sendMessage("conv-1", userMessage)).rejects.toBeInstanceOf(
      ChatTransportError,
    );
  });

  it("aborts and throws a ChatTransportError on timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => {
              reject(new DOMException("Aborted", "AbortError"));
            });
          }),
      ),
    );
    const transport = new HttpChatTransport({ baseUrl: "http://api.local", timeoutMs: 5 });

    await expect(transport.sendMessage("conv-1", userMessage)).rejects.toBeInstanceOf(
      ChatTransportError,
    );
  });
});
