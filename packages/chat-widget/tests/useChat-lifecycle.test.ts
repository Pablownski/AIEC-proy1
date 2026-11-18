import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChat } from "../src/hooks/useChat";
import type { ChatMessage } from "../src/types/chat";
import { richReply } from "./presentation-fixture";

describe("latest operation and cancellation", () => {
  it("ignores a superseded late reply and only notifies for the current response", async () => {
    let first!: (value: ChatMessage) => void;
    let second!: (value: ChatMessage) => void;
    const transport = { sendMessage: vi.fn()
      .mockImplementationOnce(() => new Promise<ChatMessage>((r) => { first = r; }))
      .mockImplementationOnce(() => new Promise<ChatMessage>((r) => { second = r; })) };
    const onReply = vi.fn();
    const { result } = renderHook(() => useChat({ transport, onReply }));
    act(() => result.current.sendMessage("Primera"));
    act(() => result.current.sendMessage("Segunda"));
    await act(async () => second({ ...richReply, id: "latest" }));
    await act(async () => first({ ...richReply, id: "old" }));
    expect(result.current.messages.filter((m) => m.role === "assistant").map((m) => m.id)).toEqual(["latest"]);
    expect(onReply).toHaveBeenCalledTimes(1);
  });

  it.each(["resolve", "reject"])("cancel ignores a late %s and resets status without a fake error", async (mode) => {
    let resolve!: (value: ChatMessage) => void;
    let reject!: (value: Error) => void;
    const transport = { sendMessage: () => new Promise<ChatMessage>((r, j) => { resolve = r; reject = j; }) };
    const onCancel = vi.fn(), onReply = vi.fn(), onFailure = vi.fn();
    const { result } = renderHook(() => useChat({ transport, onCancel, onReply, onFailure }));
    act(() => result.current.sendMessage("Hola"));
    act(() => result.current.cancel());
    await act(async () => { if (mode === "resolve") resolve(richReply); else reject(new Error("late")); });
    expect(result.current.status).toBe("idle");
    expect(result.current.messages).toHaveLength(1);
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onReply).not.toHaveBeenCalled();
    expect(onFailure).not.toHaveBeenCalled();
  });

  it("ignores pending success and failure after unmount", async () => {
    for (const fails of [false, true]) {
      let settle!: () => void;
      const transport = { sendMessage: () => new Promise<ChatMessage>((resolve, reject) => {
        settle = () => fails ? reject(new Error("late")) : resolve(richReply);
      }) };
      const onReply = vi.fn(), onFailure = vi.fn();
      const { result, unmount } = renderHook(() => useChat({ transport, onReply, onFailure }));
      act(() => result.current.sendMessage("Hola"));
      unmount();
      await act(async () => settle());
      expect(onReply).not.toHaveBeenCalled();
      expect(onFailure).not.toHaveBeenCalled();
    }
  });
});
