import { useState } from "react";
import type { CheckinFormItem } from "../api/types";
import { snapToStep } from "../lib/wellbeing";
import { Arrow } from "./WellbeingMarks";

interface Props {
  item: CheckinFormItem;
  value: number | null;
  onChange: (v: number) => void;
}

/** −/+ stepper with an editable value; the row label points at `ci-{key}`. */
export function HoursStepper({ item, value, onChange }: Props) {
  const min = item.min ?? 0;
  const max = item.max ?? 24;
  const step = item.step ?? 0.5;
  // Raw text while typing; committed (clamped and snapped) on blur or Enter.
  const [draft, setDraft] = useState<string | null>(null);

  const commit = () => {
    if (draft === null) return;
    const n = Number(draft.replace(",", "."));
    if (draft.trim() !== "" && Number.isFinite(n)) onChange(snapToStep(n, min, max, step));
    setDraft(null);
  };
  const bump = (dir: 1 | -1) => onChange(snapToStep((value ?? min) + dir * step, min, max, step));

  return (
    <div className="wb-stepper">
      <button
        type="button"
        className="wb-stepper__btn"
        aria-label="Minus half an hour"
        disabled={value === null || value <= min}
        onClick={() => bump(-1)}
      >
        <Arrow d="M6 12h12" size={22} />
      </button>
      <input
        id={`ci-${item.key}`}
        className="wb-stepper__input wb-mono"
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={draft ?? (value === null ? "" : String(value))}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
      />
      <button
        type="button"
        className="wb-stepper__btn"
        aria-label="Plus half an hour"
        disabled={value !== null && value >= max}
        onClick={() => bump(1)}
      >
        <Arrow d="M12 6v12M6 12h12" size={22} />
      </button>
      <span className="wellbeing__note">
        h · {min}–{max}, steps of {step}
      </span>
    </div>
  );
}
