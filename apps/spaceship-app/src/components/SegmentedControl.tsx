interface Props<K extends string> {
  /** Accessible name of the group, e.g. "Periodo". */
  label: string;
  options: { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}

/** Small exclusive choice (time range, which series to plot). */
export function SegmentedControl<K extends string>({ label, options, value, onChange }: Props<K>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          className={o.key === value ? "segmented__btn segmented__btn--active" : "segmented__btn"}
          aria-pressed={o.key === value}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
