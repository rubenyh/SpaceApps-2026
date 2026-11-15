import type { ReactNode } from "react";
import type { SensorStatus } from "../api/types";
import { TRACK_SCALE, explain, shownStatus } from "../lib/estado";
import { rangeText, readingValueText, unitLabel } from "../lib/format";
import { ColorSwatch } from "./ColorSwatch";
import { FlapSkeleton } from "./Flap";
import { RangeTrack } from "./RangeTrack";
import { ReadingCard } from "./ReadingCard";
import { StateIcon, type VisualState } from "./StatusPill";

interface Props {
  title: string;
  organ: string;
  /** Sensor entry of the status response, or null when it is missing. */
  sensor: SensorStatus | null;
  ageSeconds: number | null;
  /** False until the first response arrives: draws a skeleton. */
  loaded: boolean;
  /** The service is unreachable: known values are drawn as stale. */
  offline: boolean;
  size?: "sm" | "md" | "lg";
  showSource?: boolean;
  tag?: ReactNode;
  /** Extra content under the range, e.g. a chart. */
  children?: ReactNode;
}

/** ReadingCard filled from one sensor of the service status. Never invents a value or a range. */
export function SensorCard({
  title,
  organ,
  sensor,
  ageSeconds,
  loaded,
  offline,
  size,
  showSource = false,
  tag,
  children,
}: Props) {
  if (!loaded) {
    return (
      <section className="card card--skeleton" aria-hidden="true">
        <FlapSkeleton tiles={4} />
      </section>
    );
  }

  const shown = shownStatus(sensor, offline);
  const range = sensor ? rangeText(sensor.config) : null;
  const scale = sensor ? TRACK_SCALE[sensor.kind] : undefined;
  // A sample-validity range says whether the sample is usable. Out of range is "doubtful", never an alert.
  const validity = sensor?.config.range_role === "sample_validity";
  const judged = sensor?.status === "normal" || sensor?.status === "alert";
  const status: VisualState = validity && shown === "alert" ? "doubtful" : shown;

  let bottom: ReactNode;
  if (sensor?.kind === "urine_color") {
    bottom = <span className="card__note">Color shown as measured by the sensor.</span>;
  } else if (sensor && validity && range) {
    bottom = (
      <span className="card__note card__note--icon">
        {judged ? <StateIcon state={sensor.status === "alert" ? "doubtful" : "normal"} /> : null}
        {sensor.status === "alert"
          ? `Doubtful sample: outside ${range}`
          : sensor.status === "normal"
            ? `Valid sample (${range})`
            : `The sample is valid within ${range}`}
      </span>
    );
  } else if (sensor && scale && range) {
    bottom = (
      <RangeTrack value={sensor.latest?.value ?? null} scale={scale} config={sensor.config} status={shown} />
    );
  } else if (sensor && range) {
    bottom = (
      <span className="card__note card__note--icon">
        {sensor.config.provisional ? <span className="prov">PROV.</span> : null}
        Range: {range}
      </span>
    );
  } else {
    bottom = <span className="card__note">No reference range defined yet.</span>;
  }

  return (
    <ReadingCard
      title={title}
      organ={organ}
      status={status}
      value={
        sensor?.kind === "urine_color" ? (
          <ColorSwatch value={sensor.latest?.value_text} />
        ) : (
          readingValueText(sensor?.latest)
        )
      }
      unit={sensor?.kind === "urine_color" ? "" : unitLabel(sensor?.latest?.unit)}
      ageSeconds={ageSeconds}
      quality={sensor?.latest?.quality}
      source={showSource ? sensor?.latest?.source : null}
      size={size}
      explanation={validity && judged && !offline ? "Not a health reading" : explain(sensor, offline)}
      tag={tag}
    >
      {bottom}
      {children}
    </ReadingCard>
  );
}
