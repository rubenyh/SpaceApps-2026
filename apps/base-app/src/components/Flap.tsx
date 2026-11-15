import { useEffect, useRef, useState } from "react";
import { cascadeFrames } from "../lib/board.ts";

interface Props {
  text: string;
  /** One tile per character, right-aligned to `width` tiles (numbers). Otherwise one plate. */
  tiles?: boolean;
  width?: number;
  /** Ticking values (ages, clocks) swap without the cascade. */
  animate?: boolean;
  className?: string;
}

const CASCADE_MS = 240;
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Split-flap text: a changed value cascades character by character in its fixed cells. */
export function Flap({ text, tiles = false, width = 0, animate = true, className = "" }: Props) {
  const target = (tiles ? text.padStart(width) : text).toUpperCase();
  const [shown, setShown] = useState(target);
  const shownRef = useRef(target);

  useEffect(() => {
    const from = shownRef.current;
    if (from === target) return;
    const frames = animate && !reducedMotion() ? cascadeFrames(from, target) : [target];
    const step = Math.max(16, Math.floor(CASCADE_MS / frames.length));
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = () => {
      shownRef.current = frames[i];
      setShown(frames[i]);
      i += 1;
      if (i < frames.length) timer = setTimeout(tick, step);
    };
    tick();
    return () => clearTimeout(timer);
  }, [target, animate]);

  return (
    <span className={`flap ${tiles ? "flap--tiles" : "flap--plate"} ${className}`}>
      <span className="sr-only">{text}</span>
      <span className="flap__face" aria-hidden="true">
        {tiles
          ? [...shown].map((ch, i) => (
              <span key={i} className="flap__tile">
                {ch === " " ? "\u00a0" : ch}
              </span>
            ))
          : shown}
      </span>
    </span>
  );
}

/** Blank flaps while the first data loads. */
export function FlapSkeleton({ tiles = 3 }: { tiles?: number }) {
  return (
    <span className="flap flap--tiles flap--skeleton" aria-hidden="true">
      <span className="flap__face">
        {Array.from({ length: tiles }, (_, i) => (
          <span key={i} className="flap__tile">
            {"\u00a0"}
          </span>
        ))}
      </span>
    </span>
  );
}
