import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { MarkdownRenderer } from "./MarkdownRenderer";

export interface RevealedMarkdownProps {
  content: string;
  revealing: boolean;
  operation: number;
  onComplete?: (operation: number) => void;
}

/** Never parse incomplete Markdown. The preview is plain React text from the sanitized tree. */
export function RevealedMarkdown({ content, revealing, operation, onComplete }: RevealedMarkdownProps) {
  const reduced = useReducedMotion();
  const full = useRef<HTMLDivElement>(null);
  const [preview, setPreview] = useState("");
  const active = revealing && !reduced;
  // Reuse the same parsed tree rather than reparsing long Markdown every 30 ms.
  const formatted = useMemo(() => <MarkdownRenderer content={content} />, [content]);

  useEffect(() => {
    if (!revealing) return;
    if (reduced) { onComplete?.(operation); return; }
    const copy = full.current!.cloneNode(true) as HTMLDivElement;
    for (const block of copy.querySelectorAll("p,li,pre,blockquote,h1,h2,h3,h4,h5,h6,tr,br")) {
      block.appendChild(document.createTextNode("\n"));
    }
    const characters = Array.from((copy.textContent ?? "").trim());
    setPreview("");
    if (characters.length === 0) { onComplete?.(operation); return; }
    const step = Math.max(1, Math.ceil(characters.length / 200));
    let cursor = 0;
    const timer = setInterval(() => {
      cursor = Math.min(characters.length, cursor + step);
      setPreview(characters.slice(0, cursor).join(""));
      if (cursor === characters.length) {
        clearInterval(timer);
        onComplete?.(operation);
      }
    }, 30);
    return () => clearInterval(timer);
  }, [content, revealing, operation, onComplete, reduced]);

  return (
    <>
      {active && <div className="agichat-message-preview" aria-hidden="true"
        style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{preview}</div>}
      {active && <span role="status" style={{ position: "absolute", width: 1, height: 1,
        overflow: "hidden", clipPath: "inset(50%)" }}>Presentando respuesta…</span>}
      <div ref={full} hidden={active}>
        {formatted}
      </div>
    </>
  );
}
