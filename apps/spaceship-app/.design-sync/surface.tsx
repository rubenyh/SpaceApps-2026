import type { ReactNode } from "react";

// Preview cards force a white body; the console only ever renders on its dark --bg (set on body by styles.css).
export const S = ({ children }: { children: ReactNode }) => (
  <div style={{ background: "var(--bg)", padding: 16 }}>{children}</div>
);
