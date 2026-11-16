import type { ChatMessage } from "../types/chat";
import { validAction, type ExternalAction } from "../types/presentation";

export interface ReservedTab {
  closed: boolean;
  opener: unknown;
  location: { replace(url: string): void };
  close(): void;
}

export function referenceIntent(text: string): boolean {
  return referenceTargets(text).length > 0;
}

export function referenceTargets(text: string): ExternalAction["target"][] {
  text = text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  if (/\bno\s+(?:quiero\s+)?(?:abr\w*|compar\w*)/.test(text)) return [];
  if (/\b(compar\w*|adaptacion)\b/.test(text)) return ["imdb", "google_books"];
  if (!/\b(abre|abreme|abrir|open)\b/.test(text)) return [];
  const targets: ExternalAction["target"][] = [];
  if (text.includes("imdb")) targets.push("imdb");
  if (text.includes("books") || text.includes("libro")) targets.push("google_books");
  return targets.length ? targets : ["imdb", "google_books"];
}

/** Reserve only during a user gesture. No asynchronous window.open or named-window reuse. */
export class ReferenceTabs {
  private slots: Partial<Record<ExternalAction["target"], ReservedTab | null>> = {};
  private seen = new Set<string>();
  private active = false;
  private timeout: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly fallback: (actions: ExternalAction[]) => void,
    private readonly open: () => ReservedTab | null = () => window.open("about:blank", "_blank"),
  ) {}

  reserve(text: string): void {
    this.cancel();
    this.fallback([]);
    const targets = referenceTargets(text);
    if (!targets.length) return;
    this.active = true;
    for (const target of targets) {
      let tab: ReservedTab | null = null;
      try {
        tab = this.open();
        // `noopener` in window.open returns null even on success. Detach immediately instead,
        // while retaining a handle to our own blank tab for later verified navigation.
        if (tab) tab.opener = null;
        this.slots[target] = tab;
      } catch { try { tab?.close(); } catch { /* Already closed. */ } this.slots[target] = null; }
    }
    this.timeout = setTimeout(() => this.cancel(), 75000);
  }

  complete(message: ChatMessage): void {
    const blocked: ExternalAction[] = [];
    if (this.active) {
      for (const action of message.metadata?.actions ?? []) {
        if (!validAction(action) || this.seen.has(action.id)) continue;
        this.seen.add(action.id);
        const tab = this.slots[action.target];
        delete this.slots[action.target];
        try {
          if (!tab || tab.closed) { blocked.push(action); continue; }
          tab.location.replace(action.url);
        } catch {
          try { tab?.close(); } catch { /* The browser may already have closed it. */ }
          blocked.push(action);
        }
      }
    } else {
      // Expired reservation or blocked activation: never create a popup after an async reply.
      for (const action of message.metadata?.actions ?? []) {
        if (validAction(action) && !this.seen.has(action.id)) blocked.push(action);
      }
    }
    this.cancel();
    this.fallback(blocked);
  }

  cancel(): void {
    if (this.timeout) clearTimeout(this.timeout);
    for (const tab of Object.values(this.slots)) {
      try { if (tab && !tab.closed) tab.close(); } catch { /* No foreign tab is reused. */ }
    }
    this.slots = {};
    this.active = false;
  }
}
