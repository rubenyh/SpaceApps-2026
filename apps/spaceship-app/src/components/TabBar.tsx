import { useRef, type KeyboardEvent } from "react";
import { STATE_LABELS, StateIcon } from "./StatusPill";

export interface TabDef<K extends string> {
  key: K;
  label: string;
}

interface Props<K extends string> {
  tabs: TabDef<K>[];
  active: K;
  onChange: (key: K) => void;
  /** Problem to flag next to a tab label (the worst state behind that tab). */
  flags?: Partial<Record<K, "alert" | "stale" | null>>;
  /** No crew member selected: every tab is disabled. */
  disabled?: boolean;
}

export function TabBar<K extends string>({ tabs, active, onChange, flags, disabled = false }: Props<K>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = tabs.findIndex((t) => t.key === active);
    const last = tabs.length - 1;
    let next: number;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = idx === last ? 0 : idx + 1;
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = idx === 0 ? last : idx - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else return;
    onChange(tabs[next].key);
    refs.current[next]?.focus();
    e.preventDefault();
  };

  return (
    <div className="tabbar" role="tablist" aria-label="Screens" aria-orientation="vertical" onKeyDown={onKeyDown}>
      {tabs.map((t, i) => {
        const selected = t.key === active;
        const flag = flags?.[t.key] ?? null;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.key}`}
            aria-selected={selected}
            aria-controls="screen"
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            className={selected ? "tab tab--active" : "tab"}
            onClick={() => onChange(t.key)}
          >
            {t.label}
            {flag ? (
              <span className={`tab__flag tab__flag--${flag}`}>
                <StateIcon state={flag} />
                <span className="sr-only">({STATE_LABELS[flag]})</span>
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
