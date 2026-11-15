import type { ReactNode } from "react";

/** Barlow Condensed has no "₂" glyph: draw it as a subscript 2 (as in the ground console). */
export function withSub2(text: string): ReactNode {
  const parts = text.split("₂");
  if (parts.length === 1) return text;
  // One span so a flex parent with a gap does not split the label apart.
  return <span>{parts.flatMap((p, i) => (i ? [<sub key={i}>2</sub>, p] : [p]))}</span>;
}
