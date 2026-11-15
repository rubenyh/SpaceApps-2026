import type { CheckinFormItem } from "../api/types";

interface Props {
  item: CheckinFormItem;
  value: number | null;
  onChange: (v: number) => void;
}

/** One check-in scale question as a row: prompt | min label, value buttons, max label. */
export function ScaleInput({ item, value, onChange }: Props) {
  const min = item.min ?? 0;
  const max = item.max ?? 4;
  const step = item.step ?? 1;
  const values: number[] = [];
  for (let v = min; v <= max + 1e-9; v += step) values.push(Number(v.toFixed(6)));

  return (
    <fieldset className="wb-ci__row">
      <legend className="wb-ci__q">{item.prompt}</legend>
      <div className="wb-scale">
        <span className="wb-scale__end wb-scale__end--min">{item.min_label}</span>
        <div className="wb-scale__opts">
          {values.map((v) => (
            <button
              key={v}
              type="button"
              className="wb-scale__btn wb-mono"
              aria-pressed={value === v}
              onClick={() => onChange(v)}
            >
              {v}
            </button>
          ))}
        </div>
        <span className="wb-scale__end">{item.max_label}</span>
        {item.higher_is_better === false ? (
          <span className="wellbeing__faint">
            {item.key === "stress" ? `Here, ${max} means more stress` : "Here, a higher number means more of it"}
          </span>
        ) : null}
      </div>
    </fieldset>
  );
}
