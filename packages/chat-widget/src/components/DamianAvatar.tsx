import { useEffect, useState } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { damianSprites, type AvatarState } from "./damian-sprites";

export interface DamianAvatarProps {
  state?: AvatarState;
  name?: string;
}

const labels: Record<AvatarState, string> = {
  idle: "en espera", thinking: "pensando", talking: "respondiendo",
  done: "respuesta completada", error: "error en la solicitud",
};

/** Controlled avatar: terminal-state duration belongs to the chat presentation lifecycle. */
export function DamianAvatar({ state = "idle", name = "Damián" }: DamianAvatarProps) {
  const reduced = useReducedMotion();

  useEffect(() => {
    // Warm the approved local assets so changing frames does not wait on a download.
    for (const src of Object.values(damianSprites).flat()) {
      const image = new Image();
      image.src = src;
    }
  }, []);

  return (
    <span className="agichat-avatar" role="img" aria-label={`${name}: ${labels[state]}`}
      data-state={state} style={{ display: "inline-block", flexShrink: 0,
        width: "clamp(64px, 12vw, 80px)", height: "clamp(64px, 12vw, 80px)" }}>
      <AvatarFrame key={`${state}:${reduced}`} state={state} reduced={reduced} />
    </span>
  );
}

function AvatarFrame({ state, reduced }: { state: AvatarState; reduced: boolean }) {
  const [index, setIndex] = useState(0);
  const frames = damianSprites[state];
  useEffect(() => {
    if (reduced || frames.length === 1) return;
    const timer = setInterval(() => setIndex((previous) => (previous + 1) % frames.length),
      state === "thinking" ? 200 : 180);
    return () => clearInterval(timer);
  }, [state, frames, reduced]);
  return <img src={frames[index]} alt="" aria-hidden="true" width={418} height={418}
    draggable={false} style={{ display: "block", width: "100%", height: "100%",
      objectFit: "contain", imageRendering: "pixelated" }} />;
}
