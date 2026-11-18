import { useCallback, useEffect, useRef, useState } from "react";
import type { AvatarState } from "../components/damian-sprites";
import type { ChatMessage } from "../types/chat";
import { useReducedMotion } from "./useReducedMotion";

interface Presentation {
  phase: AvatarState;
  operation: number;
  replyId?: string;
}

export function useChatPresentation() {
  const reduced = useReducedMotion();
  const serial = useRef(0);
  const [presentation, setPresentation] = useState<Presentation>({ phase: "idle", operation: 0 });

  const start = useCallback(() => {
    setPresentation({ phase: "thinking", operation: ++serial.current });
  }, []);
  const cancel = useCallback(() => {
    setPresentation({ phase: "idle", operation: ++serial.current });
  }, []);
  const receive = useCallback((message: ChatMessage) => {
    setPresentation({ phase: reduced ? "done" : "talking", operation: serial.current,
      replyId: message.id });
  }, [reduced]);
  const fail = useCallback(() => {
    setPresentation({ phase: "error", operation: serial.current });
  }, []);
  const finish = useCallback((operation: number) => {
    if (operation !== serial.current) return;
    setPresentation((previous) => previous.operation === operation && previous.phase === "talking"
      ? { ...previous, phase: "done" } : previous);
  }, []);

  useEffect(() => {
    if (presentation.phase !== "done" && presentation.phase !== "error") return;
    const { operation } = presentation;
    const timer = setTimeout(() => {
      if (operation === serial.current) {
        setPresentation((previous) => ({ ...previous, phase: "idle" }));
      }
    }, 3000);
    return () => clearTimeout(timer);
  }, [presentation]);

  return { ...presentation, start, cancel, receive, fail, finish };
}
