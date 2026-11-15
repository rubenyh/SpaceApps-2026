import { useState, type FormEvent } from "react";
import { HttpError, toApiError } from "../../api/client";
import type { Checkin, CheckinUpsert } from "../../api/types";
import { getCheckinForm, getWellbeingParameters, listCheckins, putCheckin } from "../../api/wellbeing";
import { HoursStepper } from "../../components/HoursStepper";
import { ScaleInput } from "../../components/ScaleInput";
import { WellbeingServiceBanner } from "../../components/WellbeingServiceBanner";
import { Arrow, CHEVRON, WellbeingIcon } from "../../components/WellbeingMarks";
import { usePolling } from "../../hooks/usePolling";
import { firstName, formatClock, formatDayLong, missionDay } from "../../lib/wellbeing";

interface Props {
  astronautId: string;
  displayName: string;
  onBack: () => void;
}

const POLL_MS = 300_000;
const TEXT_MAX = 500;

/** Daily check-in, rendered from GET /wellbeing/checkin-form. Today's check-in can be edited. */
export function CheckinView({ astronautId, displayName, onBack }: Props) {
  const form = usePolling("wb-checkin-form", getCheckinForm, POLL_MS);
  const params = usePolling("wb-params", getWellbeingParameters, POLL_MS);
  const tz = params.data?.mission_tz;
  const today = tz ? missionDay(tz) : null;
  const existing = usePolling(
    today ? `wb-checkin:${astronautId}:${today}` : null,
    (s) => listCheckins(astronautId, { since: today ?? undefined, until: today ?? undefined }, s),
    POLL_MS,
  );

  // Unsaved changes over the loaded check-in; empty = nothing changed.
  const [edits, setEdits] = useState<Record<string, number | string>>({});
  const [saved, setSaved] = useState<Checkin | null>(null);
  const [showSaved, setShowSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = saved ?? existing.data?.[0] ?? null;
  const loaded = (key: string) => (current ? (current as unknown as Record<string, unknown>)[key] : null);
  const numberOf = (key: string): number | null => {
    const v = edits[key] ?? loaded(key);
    return typeof v === "number" ? v : null;
  };
  const textOf = (key: string): string => {
    const v = edits[key] ?? loaded(key);
    return typeof v === "string" ? v : "";
  };
  const set = (key: string, v: number | string) => setEdits((s) => ({ ...s, [key]: v }));

  const items = form.data?.items ?? [];
  const questions = items.filter((i) => i.kind !== "text");
  const complete = items.every((i) => i.kind === "text" || i.optional || numberOf(i.key) !== null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!today || !complete || saving) return;
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = { source: "crew" };
    for (const i of items) {
      if (i.kind === "text") body[i.key] = textOf(i.key).trim() === "" ? null : textOf(i.key);
      else body[i.key] = numberOf(i.key);
    }
    try {
      setSaved(await putCheckin(astronautId, today, body as unknown as CheckinUpsert));
      setEdits({});
      setShowSaved(true);
      existing.refresh();
    } catch (err) {
      const apiError = toApiError(err);
      setError(apiError instanceof HttpError ? apiError.detail : "Onboard service unreachable. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const loadError = form.error ?? params.error ?? existing.error;
  const ready = form.data !== null && today !== null && existing.data !== null;
  const back = (
    <button type="button" className="btn btn--ghost wb-back" onClick={onBack}>
      <Arrow d={CHEVRON.left} />
      Back to Personal
    </button>
  );

  return (
    <div className="screen">
      <div className="wellbeing__bar">
        {back}
        <h1 className="wb-h1">Daily check-in{today ? ` · ${formatDayLong(today)}` : ""}</h1>
        {form.data ? (
          <span className="wellbeing__note">
            About {form.data.estimated_seconds} seconds · {questions.length} questions
          </span>
        ) : null}
        <span className="wellbeing__spacer" />
        {current && !showSaved ? (
          <span className="wb-done">
            <WellbeingIcon kind="ok" size={18} />
            Submitted {formatClock(current.submitted_at, tz)} · editing
          </span>
        ) : null}
      </div>

      <WellbeingServiceBanner
        error={loadError}
        updatedAt={form.updatedAt}
        timeZone={tz}
        onRetry={() => {
          form.refresh();
          params.refresh();
          existing.refresh();
        }}
      />

      {!ready ? (
        loadError ? null : (
          <div className="banner" role="status">
            <div className="banner__text">
              <span className="banner__title">Loading…</span>
            </div>
          </div>
        )
      ) : showSaved && saved ? (
        <section className="wb-saved" aria-labelledby="wb-saved-h">
          <WellbeingIcon kind="ok" size={28} />
          <div className="wb-saved__text">
            <strong id="wb-saved-h">Check-in saved</strong>
            <span>
              Thank you, {firstName(displayName)}. Today · {formatClock(saved.submitted_at, tz)}
            </span>
          </div>
          <button type="button" className="btn btn--ghost" onClick={() => setShowSaved(false)}>
            Edit
          </button>
          {back}
        </section>
      ) : (
        <form className={`wb-ci${loadError ? " wellbeing--stale" : ""}`} aria-label="Daily check-in" onSubmit={onSubmit}>
          {items.map((i) => {
            if (i.kind === "scale") {
              return <ScaleInput key={i.key} item={i} value={numberOf(i.key)} onChange={(v) => set(i.key, v)} />;
            }
            if (i.kind === "hours") {
              return (
                <div key={i.key} className="wb-ci__row">
                  <label htmlFor={`ci-${i.key}`} className="wb-ci__q">
                    {i.prompt}
                  </label>
                  <HoursStepper item={i} value={numberOf(i.key)} onChange={(v) => set(i.key, v)} />
                </div>
              );
            }
            const max = i.max_length ?? TEXT_MAX;
            const text = textOf(i.key);
            return (
              <div key={i.key} className="wb-ci__row wb-ci__row--text">
                <label htmlFor={`ci-${i.key}`} className="wb-ci__q wb-ci__q--text">
                  {i.prompt}
                  <span className="wb-ci__private">
                    <WellbeingIcon kind="lock" size={16} />
                    Private. Never shown to the crew.
                  </span>
                </label>
                <div className="wb-input">
                  <textarea
                    id={`ci-${i.key}`}
                    rows={2}
                    maxLength={max}
                    value={text}
                    onChange={(e) => set(i.key, e.target.value)}
                  />
                  <span className="wb-ci__count wb-mono">
                    {text.length} / {max}
                  </span>
                </div>
              </div>
            );
          })}

          {error ? (
            <p className="wb-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="wb-actions wb-ci__actions">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={Object.keys(edits).length === 0}
              onClick={() => setEdits({})}
            >
              Discard changes
            </button>
            <button type="submit" className="btn" disabled={!complete || saving}>
              {saving ? "Saving…" : "Save today's check-in"}
            </button>
          </div>
          <p className="wellbeing__faint wb-ci__edit-note">You can edit today's check-in until midnight station time.</p>
        </form>
      )}
    </div>
  );
}
