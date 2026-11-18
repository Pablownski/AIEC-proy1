import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChatPresentation } from "../src/hooks/useChatPresentation";
import { richReply } from "./presentation-fixture";
import { mockMotion } from "./motion-fixture";

beforeEach(() => { vi.useFakeTimers(); mockMotion(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("chat presentation lifecycle", () => {
  it("waits for actual reveal completion, celebrates for exactly 3000 ms, then idles", () => {
    const { result } = renderHook(useChatPresentation);
    expect(result.current.phase).toBe("idle");
    act(() => result.current.start());
    expect(result.current.phase).toBe("thinking");
    act(() => result.current.receive(richReply));
    expect(result.current.phase).toBe("talking");
    act(() => vi.advanceTimersByTime(9000));
    expect(result.current.phase).toBe("talking");
    act(() => result.current.finish(result.current.operation));
    expect(result.current.phase).toBe("done");
    act(() => vi.advanceTimersByTime(2999));
    expect(result.current.phase).toBe("done");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.phase).toBe("idle");
  });

  it("holds errors for exactly 3000 ms", () => {
    const { result } = renderHook(useChatPresentation);
    act(() => result.current.start());
    act(() => result.current.fail());
    expect(result.current.phase).toBe("error");
    act(() => vi.advanceTimersByTime(2999));
    expect(result.current.phase).toBe("error");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.phase).toBe("idle");
  });

  it.each(["done", "error"] as const)("new request interrupts %s and invalidates old callbacks", (phase) => {
    const { result } = renderHook(useChatPresentation);
    act(() => result.current.start());
    if (phase === "error") act(() => result.current.fail());
    else {
      act(() => result.current.receive(richReply));
      act(() => result.current.finish(result.current.operation));
    }
    const previous = result.current.operation;
    act(() => vi.advanceTimersByTime(1500));
    act(() => {
      result.current.start();
      vi.advanceTimersByTime(1500); // Even before React commits, the serial guards the old timeout.
    });
    expect(result.current.phase).toBe("thinking");
    act(() => result.current.finish(previous));
    expect(result.current.phase).toBe("thinking");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels an operation and releases terminal timers on unmount", () => {
    const { result, unmount } = renderHook(useChatPresentation);
    act(() => result.current.start());
    act(() => result.current.cancel());
    expect(result.current.phase).toBe("idle");
    act(() => result.current.start());
    act(() => result.current.fail());
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("completes a fast response immediately with reduced motion", () => {
    mockMotion(true);
    const { result } = renderHook(useChatPresentation);
    act(() => { result.current.start(); result.current.receive(richReply); });
    expect(result.current.phase).toBe("done");
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.phase).toBe("idle");
  });
});
