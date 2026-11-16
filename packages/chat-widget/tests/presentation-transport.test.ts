import { describe, expect, it, vi } from "vitest";
import { HttpChatTransport } from "../src/transport/http-transport";
import { WebSocketChatTransport, type WebSocketLike } from "../src/transport/websocket-transport";
import { metadata, richReply, wireReply } from "./presentation-fixture";

describe("structured transport parity", () => {
  it("preserves optional metadata over HTTP", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => wireReply }));
    expect((await new HttpChatTransport({ baseUrl: "http://api.test" }).sendMessage("one", richReply)).metadata).toEqual(metadata);
    vi.unstubAllGlobals();
  });
  it.each(["valid", "invalid", "malformed"])("validates WebSocket metadata: %s", async (mode) => {
    const listeners: Record<string, Array<(event: unknown) => void>> = {};
    const socket: WebSocketLike = { readyState: 1, close: vi.fn(),
      addEventListener: (type, listener) => { (listeners[type] ??= []).push(listener); },
      removeEventListener: (type, listener) => { listeners[type] = (listeners[type] ?? []).filter((x) => x !== listener); },
      send: () => queueMicrotask(() => {
        const message = mode === "invalid" ? { ...wireReply.message, metadata: "bad" } : wireReply.message;
        for (const data of [mode === "malformed" ? "invalid-json" : JSON.stringify({ type: "agent_message", message }), JSON.stringify({ type: "agent_end" })]) {
          for (const listener of [...(listeners.message ?? [])]) listener({ data });
        }
      }),
    };
    const pending = new WebSocketChatTransport({ url: "ws://api.test", createWebSocket: () => socket }).sendMessage("one", richReply);
    if (mode === "valid") expect((await pending).metadata).toEqual(metadata);
    else await expect(pending).rejects.toThrow();
  });
});
