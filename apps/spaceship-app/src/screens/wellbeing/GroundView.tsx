import { useState, type FormEvent } from "react";
import { HttpError, toApiError } from "../../api/client";
import {
  INDICATOR_KINDS,
  type GroundInclude,
  type GroundPackage,
  type GroundPackageContent,
  type GroundRequester,
} from "../../api/types";
import {
  createGroundPackage,
  getGroundPackageContent,
  getWellbeingParameters,
  listGroundPackages,
  withdrawGroundPackage,
} from "../../api/wellbeing";
import { Panel } from "../../components/Panel";
import { SegmentedControl } from "../../components/SegmentedControl";
import { Arrow, CHEVRON, OriginMark, WellbeingIcon } from "../../components/WellbeingMarks";
import { usePolling } from "../../hooks/usePolling";
import {
  addDays,
  dayCount,
  firstName,
  formatClock,
  formatDay,
  missionDay,
  SUPPORT_LABELS,
  validPeriod,
} from "../../lib/wellbeing";

interface Props {
  astronautId: string;
  displayName: string;
  onBack: () => void;
}

const STATEMENT_VERSION = "v1";
const POLL_MS = 30_000;
const PARAMS_POLL_MS = 300_000;
const DEFAULT_DAYS = 20;

const REQUESTERS: { key: GroundRequester; label: string }[] = [
  { key: "self", label: "Myself" },
  { key: "captain", label: "Captain" },
  { key: "ground_psychologist", label: "Ground psychologist" },
];
const REQUESTER_TEXT: Record<GroundRequester, string> = {
  self: "self",
  captain: "captain",
  ground_psychologist: "ground psychologist",
};

const INCLUDES: { key: GroundInclude; label: string; hint: string }[] = [
  { key: "assessment", label: "Assessment", hint: "Level, onset, indicators" },
  { key: "timeline", label: "Timeline", hint: "Daily z per indicator" },
  { key: "checkins", label: "Check-in answers", hint: "Scores only" },
  { key: "comments", label: "My private comments", hint: "Off by default" },
];

// No code delivers packages and there is no delivery confirmation in the contract,
// so nothing is ever labeled sent or delivered.
const STATUS_LABELS = {
  queued: "Queued, not delivered",
  withdrawn: "Withdrawn",
  sent: "Left the queue, delivery not confirmed",
} as const;

const errorText = (err: unknown) => {
  const e = toApiError(err);
  return e instanceof HttpError ? e.detail : "Onboard service unreachable. Try again.";
};

const period = (from: string, to: string) => `${formatDay(from)} – ${formatDay(to)}`;
const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;

interface Preview {
  id: string;
  content: GroundPackageContent | null;
  error: string | null;
}

/** Consent screen: build a package for the ground psychologist. It only waits in the local queue. */
export function GroundView({ astronautId, displayName, onBack }: Props) {
  const params = usePolling("wb-params", getWellbeingParameters, PARAMS_POLL_MS);
  const packages = usePolling(`wb-packages:${astronautId}`, (s) => listGroundPackages(astronautId, s), POLL_MS);

  const [requestedBy, setRequestedBy] = useState<GroundRequester>("self");
  // null = default (own name for Myself, empty otherwise) until the user types.
  const [nameInput, setNameInput] = useState<string | null>(null);
  const [fromInput, setFromInput] = useState<string | null>(null);
  const [toInput, setToInput] = useState<string | null>(null);
  const [include, setInclude] = useState<Record<GroundInclude, boolean>>({
    assessment: true,
    timeline: true,
    checkins: true,
    comments: false,
  });
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);

  const tz = params.data?.mission_tz;
  const today = tz ? missionDay(tz) : null;
  const name = nameInput ?? (requestedBy === "self" ? displayName : "");
  const from = fromInput ?? (today ? addDays(today, -DEFAULT_DAYS) : "");
  const to = toInput ?? today ?? "";
  const periodOk = today !== null && validPeriod(from, to, today);
  const chosen = INCLUDES.map((i) => i.key).filter((k) => include[k]);
  const canSubmit = confirmed && chosen.length > 0 && periodOk && name.trim() !== "" && !submitting;

  const toggle = (key: GroundInclude, on: boolean) =>
    setInclude((s) => (key === "checkins" && !on ? { ...s, checkins: false, comments: false } : { ...s, [key]: on }));

  async function showPreview(id: string) {
    setPreview({ id, content: null, error: null });
    // Only the latest selection may land.
    const land = (p: Preview) => setPreview((cur) => (cur?.id === id ? p : cur));
    try {
      land({ id, content: await getGroundPackageContent(id), error: null });
    } catch (err) {
      const e = toApiError(err);
      land({
        id,
        content: null,
        error:
          e instanceof HttpError && e.status === 409
            ? "Consent withdrawn: this package can no longer be viewed."
            : errorText(err),
      });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const pkg = await createGroundPackage({
        astronaut_id: astronautId,
        requested_by: requestedBy,
        requested_by_name: name.trim(),
        consent: { astronaut_confirmed: true, statement_version: STATEMENT_VERSION },
        period_from: from,
        period_to: to,
        include: chosen,
        note: note.trim() === "" ? null : note.trim(),
      });
      setConfirmed(false);
      packages.refresh();
      void showPreview(pkg.id);
    } catch (err) {
      setSubmitError(errorText(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function withdraw(id: string) {
    setListError(null);
    try {
      await withdrawGroundPackage(id);
      packages.refresh();
      setPreview((cur) => (cur?.id === id ? null : cur));
    } catch (err) {
      setListError(errorText(err));
    }
  }

  const loadError = params.error ?? packages.error;

  return (
    <div className="screen">
      <div className="wellbeing__bar">
        <button type="button" className="btn btn--ghost wb-back" onClick={onBack}>
          <Arrow d={CHEVRON.left} />
          Back to Personal
        </button>
        <h1 className="wb-h1">Share with the ground psychologist</h1>
        <span className="wb-private">
          <WellbeingIcon kind="lock" size={18} />
          Private · {displayName}
        </span>
      </div>

      <div className="wb-callout" role="note">
        <WellbeingIcon kind="info" size={22} />
        <span>
          <strong>Nothing is sent automatically.</strong> A package waits in the local queue on board, and you can
          withdraw your consent while it is queued.
        </span>
      </div>

      {loadError ? (
        <div className="banner banner--stale" role="alert">
          <WellbeingIcon kind="service_off" size={30} />
          <div className="banner__text">
            <span className="banner__title">Wellbeing service unavailable</span>
            <span>Packages cannot be created or listed right now.</span>
          </div>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              params.refresh();
              packages.refresh();
            }}
          >
            Retry
          </button>
        </div>
      ) : null}

      {today === null ? (
        loadError ? null : (
          <div className="banner" role="status">
            <div className="banner__text">
              <span className="banner__title">Loading…</span>
            </div>
          </div>
        )
      ) : (
        <div className="wb-ground">
          <form className="wb-ground__main" onSubmit={onSubmit} aria-label="Package for the ground psychologist">
            <Panel title="What to share">
              <fieldset className="wb-fieldset">
                <legend className="wb-label">Requested by</legend>
                <SegmentedControl
                  label="Requested by"
                  options={REQUESTERS}
                  value={requestedBy}
                  onChange={(k) => {
                    setRequestedBy(k);
                    setNameInput(null);
                  }}
                />
                <span className="wellbeing__faint">
                  Whoever asks, only {firstName(displayName)} can confirm the consent below.
                </span>
              </fieldset>

              <div className="wb-ground__fields">
                <label className="wb-input wb-input--name">
                  Name of requester
                  <input
                    type="text"
                    value={name}
                    required
                    onChange={(e) => setNameInput(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label className="wb-input">
                  From
                  <input
                    type="date"
                    className="wb-mono"
                    value={from}
                    max={today}
                    required
                    onChange={(e) => setFromInput(e.target.value)}
                  />
                </label>
                <label className="wb-input">
                  To
                  <input
                    type="date"
                    className="wb-mono"
                    value={to}
                    max={today}
                    required
                    onChange={(e) => setToInput(e.target.value)}
                  />
                </label>
              </div>
              {periodOk ? null : (
                <span className="wb-hint-warn">From must be on or before To, and To cannot be after today.</span>
              )}

              <fieldset className="wb-fieldset">
                <legend className="wb-label">Include</legend>
                <div className="wb-includes">
                  {INCLUDES.map((i) => {
                    const disabled = i.key === "comments" && !include.checkins;
                    return (
                      <label
                        key={i.key}
                        className={`wb-check${include[i.key] ? " wb-check--on" : ""}${disabled ? " wb-check--disabled" : ""}`}
                      >
                        <input
                          type="checkbox"
                          checked={include[i.key]}
                          disabled={disabled}
                          onChange={(e) => toggle(i.key, e.target.checked)}
                        />
                        <span>
                          <strong>{i.label}</strong>
                          <span className="wb-check__hint">{disabled ? "Needs check-in answers" : i.hint}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <label className="wb-input">
                Note for the psychologist (optional)
                <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </Panel>

            <Panel title="Your consent">
              <p className="wb-consent__text">
                I agree to share the items selected above, for {from && to ? period(from, to) : "---"}, with the
                mission's ground psychologist. I understand this is not a diagnosis, the thresholds are provisional,
                and I can withdraw consent while the package is queued.
              </p>
              <label className="wb-check wb-check--consent">
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                <strong>I, {displayName}, confirm this myself.</strong>
              </label>
              <span className="wb-mono wellbeing__faint">Consent statement {STATEMENT_VERSION}</span>
              {submitError ? (
                <p className="wb-error" role="alert">
                  {submitError}
                </p>
              ) : null}
              <div className="wb-actions">
                <button type="submit" className="btn" disabled={!canSubmit}>
                  {submitting ? "Adding…" : "Add to local queue"}
                </button>
                <button type="button" className="btn btn--ghost" onClick={onBack}>
                  Cancel
                </button>
              </div>
            </Panel>
          </form>

          <div className="wb-ground__side">
            <Panel title="Preview of queued package">
              <PreviewBody preview={preview} />
            </Panel>

            <Panel title="Your packages">
              {listError ? (
                <p className="wb-error" role="alert">
                  {listError}
                </p>
              ) : null}
              {packages.data === null ? (
                <p className="wellbeing__note">{packages.error ? "---" : "Loading…"}</p>
              ) : packages.data.length === 0 ? (
                <p className="wellbeing__note">No packages yet.</p>
              ) : (
                <ul className="wb-pkgs">
                  {[...packages.data]
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .map((p) => (
                      <PackageItem
                        key={p.id}
                        pkg={p}
                        tz={tz ?? "UTC"}
                        selected={preview?.id === p.id}
                        onPreview={() => void showPreview(p.id)}
                        onWithdraw={() => void withdraw(p.id)}
                      />
                    ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

function PreviewBody({ preview }: { preview: Preview | null }) {
  if (preview === null) return <p className="wellbeing__note">Add a package to see exactly what would be sent.</p>;
  if (preview.error) {
    return (
      <p className="wb-notice" role="note">
        <WellbeingIcon kind="info" size={16} />
        {preview.error}
      </p>
    );
  }
  const c = preview.content;
  if (c === null) return <p className="wellbeing__note">Loading…</p>;
  const p = c.package;
  const a = c.assessment;
  return (
    <dl className="wb-preview">
      <dt>Period</dt>
      <dd>
        {period(p.period_from, p.period_to)} ({days(dayCount(p.period_from, p.period_to))})
      </dd>
      <dt>Assessment</dt>
      <dd>
        {a ? (
          <>
            {SUPPORT_LABELS[a.level]}
            {a.onset_date ? ` · since ${formatDay(a.onset_date)}` : ""} · <span className="prov">PROV.</span>
          </>
        ) : (
          "Not included"
        )}
      </dd>
      <dt>Timeline</dt>
      <dd>{c.timeline ? `${days(c.timeline.days.length)} · ${INDICATOR_KINDS.length} indicators` : "Not included"}</dd>
      <dt>Check-ins</dt>
      <dd>{c.checkins ? days(c.checkins.length) : "Not included"}</dd>
      <dt>Comments</dt>
      <dd>{p.include.includes("comments") ? "Included" : "Not included"}</dd>
      <dt>Data origin</dt>
      <dd>{a?.latest_origin ? <OriginMark origin={a.latest_origin} /> : "---"}</dd>
      <dt>Status</dt>
      <dd>{STATUS_LABELS[p.status]}</dd>
      <dt>Exact content</dt>
      <dd>
        <details>
          <summary>Show the package exactly as stored</summary>
          <pre className="wb-preview__json">{JSON.stringify(c, null, 2)}</pre>
        </details>
      </dd>
    </dl>
  );
}

interface ItemProps {
  pkg: GroundPackage;
  tz: string;
  selected: boolean;
  onPreview: () => void;
  onWithdraw: () => void;
}

function PackageItem({ pkg, tz, selected, onPreview, onWithdraw }: ItemProps) {
  const recorded = pkg.consent_recorded_at;
  return (
    <li className={`wb-pkg wb-pkg--${pkg.status}`}>
      <div className="wb-pkg__head">
        <strong>{period(pkg.period_from, pkg.period_to)}</strong>
        <span className={`wb-status wb-status--${pkg.status}`}>
          {pkg.status === "queued" ? <WellbeingIcon kind="stale" size={16} /> : null}
          {STATUS_LABELS[pkg.status]}
        </span>
      </div>
      <span className="wellbeing__note">
        Requested by {pkg.requested_by_name} ({REQUESTER_TEXT[pkg.requested_by]}) · consent{" "}
        {pkg.consent_statement_version} recorded {formatDay(missionDay(tz, new Date(recorded)))}{" "}
        {formatClock(recorded, tz)}
      </span>
      <div className="wb-actions">
        <button type="button" className="btn btn--ghost" aria-pressed={selected} onClick={onPreview}>
          Preview
        </button>
        {pkg.status === "queued" ? (
          <button type="button" className="btn btn--ghost" onClick={onWithdraw}>
            Withdraw consent
          </button>
        ) : null}
      </div>
    </li>
  );
}
