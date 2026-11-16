import { afterEach, describe, expect, it, vi } from "vitest";
import { ReferenceTabs, referenceTargets, referenceIntent } from "../src/actions/reference-tabs";
import { richReply } from "./presentation-fixture";

const tab = () => ({ closed: false, opener: {} as unknown, location: { replace: vi.fn() }, close: vi.fn() });
afterEach(() => vi.useRealTimers());

describe("limited browser actions", () => {
  it.each(["Hola", "Recomienda fantasía", "No quiero abrir IMDb"])("does not reserve for %s", (text) => {
    const open = vi.fn(); const tabs = new ReferenceTabs(vi.fn(), open);
    tabs.reserve(text); expect(open).not.toHaveBeenCalled();
    expect(referenceIntent(text)).toBe(false);
  });
  it("recognizes accents and limits explicit targets", () => {
    expect(referenceTargets("Compárala")).toEqual(["imdb", "google_books"]);
    expect(referenceTargets("Ábreme IMDb")).toEqual(["imdb"]);
    expect(referenceTargets("Abre Google Books")).toEqual(["google_books"]);
    expect(referenceTargets("Open references")).toEqual(["imdb", "google_books"]);
  });
  it("detaches opener, navigates only verified URLs and never repeats actions", () => {
    const a = tab(), b = tab(), fallback = vi.fn();
    const open = vi.fn().mockReturnValueOnce(a).mockReturnValueOnce(b);
    const tabs = new ReferenceTabs(fallback, open);
    tabs.reserve("Compara"); expect(a.opener).toBeNull(); expect(b.opener).toBeNull();
    tabs.complete(richReply); tabs.complete(richReply);
    expect(a.location.replace).toHaveBeenCalledOnce();
    expect(b.location.replace).toHaveBeenCalledWith("https://books.google.com/books?id=test_volume");
    expect(a.close).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledTimes(2);
  });
  it("offers links for blocked popups or closed reserved windows", () => {
    const closed = { ...tab(), closed: true }, fallback = vi.fn();
    const tabs = new ReferenceTabs(fallback, vi.fn().mockReturnValueOnce(null).mockReturnValueOnce(closed));
    tabs.reserve("Compara"); tabs.complete(richReply);
    expect(fallback).toHaveBeenLastCalledWith(richReply.metadata!.actions);
  });
  it("closes unused reservations, including failures and expiry", () => {
    vi.useFakeTimers(); const a = tab(), open = vi.fn(() => a);
    const tabs = new ReferenceTabs(vi.fn(), open);
    tabs.reserve("Abre IMDb"); tabs.complete({ ...richReply, metadata: undefined });
    expect(a.close).toHaveBeenCalledOnce();
    tabs.reserve("Abre IMDb"); vi.advanceTimersByTime(75000);
    expect(a.close).toHaveBeenCalledTimes(2);
    tabs.reserve("Abre IMDb"); tabs.cancel(); expect(a.close).toHaveBeenCalledTimes(3);
  });
  it("never opens asynchronously, ignores unsafe destinations and falls back after navigation errors", () => {
    const fallback = vi.fn(), a = tab(); a.location.replace.mockImplementation(() => { throw new Error(); });
    const tabs = new ReferenceTabs(fallback, vi.fn(() => a));
    tabs.complete(richReply); expect(fallback).toHaveBeenLastCalledWith(richReply.metadata!.actions);
    tabs.reserve("Abre IMDb"); tabs.complete({ ...richReply, metadata: { ...richReply.metadata!,
      actions: [{ ...richReply.metadata!.actions[0]!, url: "javascript:alert(1)" }] } });
    expect(a.location.replace).not.toHaveBeenCalled();
    tabs.reserve("Abre IMDb"); tabs.complete({ ...richReply, metadata: { ...richReply.metadata!, actions: [richReply.metadata!.actions[0]!] } });
    expect(fallback).toHaveBeenLastCalledWith([richReply.metadata!.actions[0]!]);
    expect(a.close).toHaveBeenCalled();
  });
  it("handles browser security errors during reservation", () => {
    const open = vi.fn(() => { throw new Error(); });
    const tabs = new ReferenceTabs(vi.fn(), open);
    expect(() => tabs.reserve("Compara")).not.toThrow(); tabs.cancel();
  });
});
