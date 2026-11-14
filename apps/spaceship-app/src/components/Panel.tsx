import type { ReactNode } from "react";

interface Props {
  title: ReactNode;
  /** Right side of the title bar (badge, buttons). */
  aside?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export function Panel({ title, aside, className, children }: Props) {
  return (
    <section className={`panel${className ? ` ${className}` : ""}`}>
      <header className="panel__title">
        <h2>{title}</h2>
        {aside ? <div className="panel__aside">{aside}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
