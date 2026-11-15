import type { ReadingStatus, SensorConfig } from "../api/types";
import { formatNumber, rangeText } from "../lib/format";
import { trackPercent } from "../lib/estado";

interface Props {
  /** Latest numeric value, or null to draw the bar without a marker. */
  value: number | null;
  /** Ends of the bar (display axis only). */
  scale: [number, number];
  /** Range, provisional flag and source come from the service config. */
  config: SensorConfig;
  status: ReadingStatus;
}

/** Rail with the normal zone bracketed and a needle at the current value. */
export function RangeTrack({ value, scale, config, status }: Props) {
  const { normal_min: min, normal_max: max } = config;
  const from = trackPercent(min ?? scale[0], scale);
  const to = trackPercent(max ?? scale[1], scale);
  const range = rangeText(config);
  return (
    <div className="track">
      <div className="track__bar" aria-hidden="true">
        <div className="track__rail" />
        {range ? (
          <div className="track__zone" style={{ left: `${from}%`, width: `${to - from}%` }} />
        ) : null}
        {value !== null && status !== "no_data" ? (
          <div
            className={`track__marker track__marker--${status}`}
            style={{ left: `calc(${trackPercent(value, scale)}% - 1px)` }}
          />
        ) : null}
      </div>
      <div className="track__scale">
        <span className="track__end">{formatNumber(scale[0])}</span>
        <span className="track__range">
          {range ? (
            <>
              {config.provisional ? <span className="prov">PROV.</span> : null}
              {range}
              {config.range_source ? ` · ${config.range_source}` : ""}
            </>
          ) : (
            "No range defined"
          )}
        </span>
        <span className="track__end">{formatNumber(scale[1])}</span>
      </div>
    </div>
  );
}
