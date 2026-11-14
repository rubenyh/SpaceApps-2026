import type { ReactNode } from "react";

interface Props {
  title: ReactNode;
  /** Right side of the title bar (segmented control, label). */
  aside?: ReactNode;
  className?: string;
  children?: ReactNode;
}

/** Titled surface for charts and lists. */
export function Panel({ title, aside, className, children }: Props) {
  return (
    <section className={`panel${className ? ` ${className}` : ""}`}>
      <header className="panel__head">
        <h2>{title}</h2>
        {aside ? <div className="panel__aside">{aside}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
