import type { ReactNode } from "react";

/** Screen frame: vignette and scanline overlays above the content (non-interactive). */
export function CrtFrame({ children }: { children: ReactNode }) {
  return (
    <div className="crt">
      <div className="crt__content">{children}</div>
      <div className="crt__vignette" aria-hidden="true" />
      <div className="crt__scanlines" aria-hidden="true" />
    </div>
  );
}
