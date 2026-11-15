import type { IndicatorState } from "../api/types";
import {
  baselineDays,
  componentLabel,
  formatDay,
  formatValue,
  formatZ,
  INDICATOR_LABELS,
  indicatorScored,
  SOURCE_LABELS,
  sourcesText,
  staleHint,
} from "../lib/wellbeing";
import { Arrow, CHEVRON, OriginMark, WellbeingPill } from "./WellbeingMarks";
import { ZTrack } from "./ZTrack";

interface Props {
  indicator: IndicatorState;
  threshold: number;
  /** WellbeingParameters.baseline_min_days: below it the indicator gets no score. */
  minDays: number;
  expanded: boolean;
  onToggle: () => void;
  /** Today's mission day, for the age of old data. */
  today?: string;
}

/** One indicator vs. the person's own usual, with its components on demand. */
export function IndicatorRow({ indicator, threshold, minDays, expanded, onToggle, today }: Props) {
  const { kind, status, components } = indicator;
  const scored = indicatorScored(indicator, minDays);
  const z = scored ? indicator.z : null;
  const detailId = `wb-ind-${kind}`;
  const base = components.find((c) => c.baseline_ready && c.baseline_days >= minDays);
  const have = baselineDays(indicator);
  const caption = [
    base
      ? `Baseline from ${base.baseline_days} days${
          base.baseline_from && base.baseline_to
            ? `, ${formatDay(base.baseline_from)} – ${formatDay(base.baseline_to)}`
            : ""
        }`
      : `Baseline pending: ${Math.min(have, minDays)} of ${minDays} days`,
    scored ? (indicator.deviant_since ? `Changed since ${formatDay(indicator.deviant_since)}` : "No sustained change") : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className={`wb-ind${expanded ? " wb-ind--open" : ""}`}>
      <div className="wb-ind__row">
        <strong>{INDICATOR_LABELS[kind]}</strong>
        <span className="wb-ind__status">
          <WellbeingPill level={status} kind="indicator" size="sm" />
          {scored ? null : <span className="sr-only"> (no score)</span>}
          <span className="prov">Provisional</span>
        </span>
        <ZTrack z={z} threshold={threshold} stale={status === "stale"} />
        <span className={`wb-ind__z wb-mono${z === null ? " wb-ind__z--none" : ""}`}>{formatZ(z)}</span>
        <span className="wb-ind__sources">{sourcesText(indicator.sources)}</span>
        <span>
          <OriginMark origin={indicator.latest_origin} />
        </span>
        <button
          type="button"
          className="btn btn--ghost wb-iconbtn"
          aria-expanded={expanded}
          aria-controls={detailId}
          aria-label={`${expanded ? "Hide" : "Show"} ${kind} components`}
          onClick={onToggle}
        >
          <Arrow d={expanded ? CHEVRON.up : CHEVRON.down} />
        </button>
      </div>
      <p className="wb-ind__hint">
        {indicator.sources.length === 0
          ? "No source has data for this indicator."
          : status === "stale"
            ? `${staleHint(indicator.latest_day, today)} ${caption}`
            : caption}
      </p>
      <div id={detailId} className="wb-ind__detail" hidden={!expanded}>
        <table className="wb-comp">
          <thead>
            <tr>
              <th scope="col">Component</th>
              <th scope="col">Source</th>
              <th scope="col" className="wb-comp__num">Latest</th>
              <th scope="col" className="wb-comp__num">Your usual (median)</th>
              <th scope="col" className="wb-comp__num">z</th>
              <th scope="col">Day · origin</th>
            </tr>
          </thead>
          <tbody>
            {components.map((c) => (
              <tr key={c.component}>
                <td>{componentLabel(c.component)}</td>
                <td className="wb-comp__muted">{SOURCE_LABELS[c.source]}</td>
                <td className="wb-comp__num wb-mono">{formatValue(c.latest_value, c.unit)}</td>
                <td className="wb-comp__num wb-mono wb-comp__muted">
                  {c.baseline_ready && c.baseline_days >= minDays
                    ? formatValue(c.baseline_median, c.unit)
                    : `Pending ${Math.min(c.baseline_days, minDays)}/${minDays} d`}
                </td>
                <td className="wb-comp__num wb-mono">
                  {c.baseline_ready && c.baseline_days >= minDays && scored ? formatZ(c.z) : "---"}
                </td>
                <td>
                  <span className="wb-comp__day">
                    <span className="wb-mono">{c.latest_day ? formatDay(c.latest_day) : "---"}</span>
                    <OriginMark origin={c.latest_origin} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
