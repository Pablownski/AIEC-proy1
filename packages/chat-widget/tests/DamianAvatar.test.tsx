import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DamianAvatar } from "../src/components/DamianAvatar";
import { damianSprites } from "../src/components/damian-sprites";
import { mockMotion } from "./motion-fixture";

beforeEach(() => { vi.useFakeTimers(); mockMotion(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const image = () => screen.getByRole("img").querySelector("img")!;

describe("approved Damian sprites", () => {
  it("starts idle with a fixed, pixelated, uncropped box", () => {
    render(<DamianAvatar />);
    expect(screen.getByRole("img")).toHaveAttribute("data-state", "idle");
    expect(image()).toHaveAttribute("src", damianSprites.idle[0]);
    expect(image()).toHaveStyle({ imageRendering: "pixelated", objectFit: "contain" });
    expect(image()).toHaveAttribute("width", "418");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cycles four thinking frames every 200 ms without transforming the image", () => {
    const { rerender } = render(<DamianAvatar state="thinking" />);
    for (let i = 0; i < 9; i++) {
      expect(image()).toHaveAttribute("src", damianSprites.thinking[i % 4]);
      expect(image().style.transform).toBe("");
      act(() => vi.advanceTimersByTime(200));
    }
    const box = screen.getByRole("img").getAttribute("style");
    rerender(<DamianAvatar state="done" />);
    expect(screen.getByRole("img").getAttribute("style")).toBe(box);
    expect(vi.getTimerCount()).toBe(0);
    rerender(<DamianAvatar state="thinking" />);
    expect(image()).toHaveAttribute("src", damianSprites.thinking[0]);
  });

  it("alternates closed/open mouth every 180 ms and resets on state change", () => {
    const { rerender, unmount } = render(<DamianAvatar state="talking" />);
    expect(image()).toHaveAttribute("src", damianSprites.talking[0]);
    act(() => vi.advanceTimersByTime(179));
    expect(image()).toHaveAttribute("src", damianSprites.talking[0]);
    act(() => vi.advanceTimersByTime(1));
    expect(image()).toHaveAttribute("src", damianSprites.talking[1]);
    act(() => vi.advanceTimersByTime(180));
    expect(image()).toHaveAttribute("src", damianSprites.talking[0]);
    rerender(<DamianAvatar state="error" />);
    expect(image()).toHaveAttribute("src", damianSprites.error[0]);
    expect(vi.getTimerCount()).toBe(0);
    rerender(<DamianAvatar state="talking" />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("uses static frames with reduced motion and cleans up preference subscriptions", () => {
    const motion = mockMotion(true);
    const { unmount } = render(<DamianAvatar state="thinking" />);
    act(() => vi.advanceTimersByTime(1000));
    expect(image()).toHaveAttribute("src", damianSprites.thinking[0]);
    expect(vi.getTimerCount()).toBe(0);
    motion.change(false);
    act(() => vi.advanceTimersByTime(200));
    expect(image()).toHaveAttribute("src", damianSprites.thinking[1]);
    motion.change(true);
    expect(image()).toHaveAttribute("src", damianSprites.thinking[0]);
    unmount();
    expect(motion.preference.removeEventListener).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
