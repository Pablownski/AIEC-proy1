import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RevealedMarkdown } from "../src/components/RevealedMarkdown";
import { AgentMessage } from "../src/components/AgentMessage";
import { richReply } from "./presentation-fixture";
import { mockMotion } from "./motion-fixture";

beforeEach(() => { vi.useFakeTimers(); mockMotion(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("safe presentation-only reveal", () => {
  it("reveals plain text and exposes complete Markdown, links and cards only at completion", () => {
    const onComplete = vi.fn();
    const message = { ...richReply, content: "## Cine\n\n**Hola** mundo\n\n- Uno\n- Dos\n\n[IMDb](https://www.imdb.com/title/tt1234567/)" };
    const { container, rerender } = render(<AgentMessage message={message} revealing operation={1} onRevealComplete={onComplete} />);
    expect(screen.queryByRole("heading", { name: "Cine" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Comparación libro y película")).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(300));
    expect(container.querySelector(".agichat-message-preview")).toHaveTextContent("Cine Hola");
    expect(container.querySelector(".agichat-message-preview")).not.toHaveTextContent("**");
    act(() => vi.advanceTimersByTime(6000));
    expect(onComplete).toHaveBeenCalledExactlyOnceWith(1);
    rerender(<AgentMessage message={message} operation={1} />);
    expect(screen.getByRole("heading", { name: "Cine" })).toBeVisible();
    expect(screen.getByText("Hola").tagName).toBe("STRONG");
    expect(screen.getByLabelText("Comparación libro y película")).toBeVisible();
    expect(screen.getByRole("link", { name: "IMDb" })).toHaveAttribute("href", "https://www.imdb.com/title/tt1234567/");
  });

  it("keeps sanitized markup safe before, during and after revealing", () => {
    const content = 'Hola <script>alert(1)</script> [malo](javascript:alert(1)) <img src="x" onerror="alert(1)">';
    const { container, rerender } = render(<RevealedMarkdown content={content} revealing operation={2} />);
    act(() => vi.advanceTimersByTime(500));
    expect(container.querySelector("script,[onerror],[onclick],a[href^='javascript:']")).toBeNull();
    rerender(<RevealedMarkdown content={content} revealing={false} operation={2} />);
    expect(container.querySelector("script,[onerror],[onclick],a[href^='javascript:']")).toBeNull();
  });

  it("preserves Unicode and bounds long-response presentation to 6000 ms", () => {
    const onComplete = vi.fn();
    const { container, rerender } = render(<RevealedMarkdown content="🐉Hola" revealing operation={1} onComplete={onComplete} />);
    act(() => vi.advanceTimersByTime(30));
    expect(container.querySelector(".agichat-message-preview")).toHaveTextContent("🐉");
    rerender(<RevealedMarkdown content={"x".repeat(12000)} revealing operation={2} onComplete={onComplete} />);
    act(() => vi.advanceTimersByTime(5999));
    expect(onComplete).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onComplete).toHaveBeenCalledExactlyOnceWith(2);
  });

  it("cancels stale reveal timers on new content, cancellation and unmount", () => {
    const onComplete = vi.fn();
    const { rerender, unmount } = render(<RevealedMarkdown content="Una respuesta" revealing operation={1} onComplete={onComplete} />);
    act(() => vi.advanceTimersByTime(60));
    rerender(<RevealedMarkdown content="Otra" revealing={false} operation={2} onComplete={onComplete} />);
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(6000));
    expect(onComplete).not.toHaveBeenCalled();
    rerender(<RevealedMarkdown content="Otra" revealing operation={3} onComplete={onComplete} />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("shows complete content immediately and interrupts active reveal for reduced motion", () => {
    const motion = mockMotion();
    const onComplete = vi.fn();
    render(<RevealedMarkdown content="**Completo**" revealing operation={3} onComplete={onComplete} />);
    motion.change(true);
    expect(screen.getByText("Completo")).toBeVisible();
    expect(onComplete).toHaveBeenCalledExactlyOnceWith(3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("finishes empty responses without starting a timer", () => {
    const onComplete = vi.fn();
    render(<RevealedMarkdown content="" revealing operation={4} onComplete={onComplete} />);
    expect(onComplete).toHaveBeenCalledExactlyOnceWith(4);
    expect(vi.getTimerCount()).toBe(0);
  });
});
