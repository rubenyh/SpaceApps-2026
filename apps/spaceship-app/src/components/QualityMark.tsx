import type { Quality } from "../api/types";
import { QUALITY_LABELS } from "../lib/format";

const BARS: Record<Quality, number> = { good: 3, suspect: 2, bad: 1 };

/** Reading quality as filled bars plus its word, so it reads without colour. */
export function QualityMark({ quality }: { quality: Quality }) {
  return (
    <span className={`quality quality--${quality}`}>
      <span className="quality__bars" aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <span key={n} className={n <= BARS[quality] ? "quality__bar quality__bar--on" : "quality__bar"} />
        ))}
      </span>
      {QUALITY_LABELS[quality] ?? quality}
    </span>
  );
}
