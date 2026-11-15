import { useRef, useState, type FormEvent } from "react";
import { firstName } from "../lib/wellbeing";
import { checkPin } from "../lib/wellbeingPins";
import { WellbeingIcon } from "./WellbeingMarks";

interface Props {
  astronautId: string;
  displayName?: string;
  onUnlock: () => void;
}

/**
 * PIN gate before any personal wellbeing detail. Renders no data and fetches nothing.
 * Contract gap #1 (no crew auth): the check is the local `shortcut:` in lib/wellbeingPins.ts.
 */
export function PersonalLock({ astronautId, displayName, onUnlock }: Props) {
  const [pin, setPin] = useState("");
  const [wrong, setWrong] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const name = firstName(displayName ?? astronautId);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (checkPin(astronautId, pin)) {
      onUnlock();
      return;
    }
    setWrong(true);
    setPin("");
    input.current?.focus();
  }

  return (
    <form className="wb-lock" aria-labelledby="wb-lock-h" onSubmit={onSubmit}>
      <WellbeingIcon kind="lock" size={40} />
      <h2 id="wb-lock-h">{name}'s personal detail is private</h2>
      <p>Only {name} can open it. The crew view shows the overall level only.</p>
      <label className="wb-input wb-lock__field">
        {name}'s PIN
        <input
          ref={input}
          type="password"
          inputMode="numeric"
          autoComplete="off"
          autoFocus
          value={pin}
          onChange={(e) => setPin(e.target.value)}
        />
      </label>
      {wrong ? (
        <p className="wb-error" role="alert">
          That PIN doesn't match. Try again.
        </p>
      ) : null}
      <button type="submit" className="btn wb-lock__btn">
        Unlock
      </button>
    </form>
  );
}
