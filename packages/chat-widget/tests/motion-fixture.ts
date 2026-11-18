import { act } from "@testing-library/react";
import { vi } from "vitest";

export function mockMotion(initial = false) {
  const listeners = new Set<() => void>();
  const preference = { matches: initial,
    addEventListener: vi.fn((_type: string, listener: () => void) => listeners.add(listener)),
    removeEventListener: vi.fn((_type: string, listener: () => void) => listeners.delete(listener)),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => preference));
  return {
    preference,
    change: (matches: boolean) => act(() => {
      preference.matches = matches;
      listeners.forEach((listener) => listener());
    }),
  };
}
