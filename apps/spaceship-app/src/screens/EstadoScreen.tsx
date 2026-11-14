import type { SensorKind, SensorStatus } from "../api/types";
import { getAstronautStatus } from "../api/status";
import { BodyMap } from "../components/BodyMap";
import { SensorCard } from "../components/SensorCard";
import { ServiceBanner } from "../components/ServiceBanner";
import { StateIcon, StatusPill } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { healthAlerts, rangeSide, shownStatus } from "../lib/estado";
import { formatAge, rangeText, readingValueText, unitLabel } from "../lib/format";
import { findSensor, liveAge } from "../lib/sensors";

type DetailTab = "vitales" | "musculo" | "orina";

interface Props {
  astronautId: string;
  /** Open the tab that holds the detail of a reading. */
  onNavigate: (tab: DetailTab) => void;
}

const POLL_MS = 5000;

/** How the top notice names a reading, and where its detail lives. */
const ALERT_COPY: Partial<Record<SensorKind, { name: string; tab: DetailTab; link: string }>> = {
  heart_rate: { name: "your heart rate", tab: "vitales", link: "View vital signs" },
  spo2: { name: "your blood oxygen", tab: "vitales", link: "View vital signs" },
  muscle_density: { name: "your muscle density value", tab: "musculo", link: "View muscle" },
  urine_ph: { name: "your urine pH", tab: "orina", link: "View urine" },
  urine_salinity: { name: "your urine salinity value", tab: "orina", link: "View urine" },
};

function AlertBanner({
  alerts,
  ageSeconds,
  onNavigate,
}: {
  alerts: SensorStatus[];
  ageSeconds: number | null;
  onNavigate: (tab: DetailTab) => void;
}) {
  const first = alerts[0];
  const copy = ALERT_COPY[first.kind];
  const side = rangeSide(first);
  const how = side === "high" ? "is high" : side === "low" ? "is low" : "is outside normal";
  const where =
    side === "high" ? "above normal" : side === "low" ? "below normal" : "outside normal";
  const range = rangeText(first.config);
  const unit = unitLabel(first.latest?.unit);
  const others = alerts.length - 1;
  return (
    <div className="banner banner--alert" role="alert">
      <StateIcon state="alert" size={30} pulse />
      <div className="banner__text">
        <span className="banner__title">
          Needs your attention: {copy?.name ?? "a reading"} {how}
        </span>
        <span>
          {readingValueText(first.latest)}
          {unit ? ` ${unit}` : ""}, {where}
          {range ? ` (${range}${first.config.provisional ? ", provisional" : ""})` : ""}.
          {ageSeconds !== null ? ` Measured ${formatAge(ageSeconds)}.` : ""}
          {others > 0 ? ` ${others} more ${others === 1 ? "alert" : "alerts"} below.` : ""}
        </span>
      </div>
      {copy ? (
        <button type="button" className="btn btn--on-alert" onClick={() => onNavigate(copy.tab)}>
          {copy.link} →
        </button>
      ) : null}
    </div>
  );
}

/** No alerts: say so without implying that stale or missing readings are fine. */
function SummaryBanner({ sensors }: { sensors: (SensorStatus | null)[] }) {
  const count = (st: string) => sensors.filter((s) => (s?.status ?? "no_data") === st).length;
  const notes = [
    count("stale") > 0 ? `${count("stale")} with old data` : "",
    count("no_data") > 0 ? `${count("no_data")} with no data` : "",
    count("no_range") > 0 ? `${count("no_range")} with no range` : "",
  ].filter(Boolean);
  return (
    <div className="banner" role="status">
      <StateIcon state={notes.length > 0 ? "no_range" : "normal"} size={30} />
      <div className="banner__text">
        <span className="banner__title">No active alerts</span>
        <span>
          {notes.length > 0
            ? `Of these 4 readings: ${notes.join(", ")}. Those cannot be evaluated.`
            : "All 4 readings are within normal."}
        </span>
      </div>
    </div>
  );
}

export function EstadoScreen({ astronautId, onNavigate }: Props) {
  const poll = usePolling(
    `estado:${astronautId}`,
    (signal) => getAstronautStatus(astronautId, signal),
    POLL_MS,
  );
  const now = useNow(1000);
  const { data, error, updatedAt, refresh } = poll;
  const loaded = data !== null;
  const offline = error !== null;

  const heart = findSensor(data, "heart_rate");
  const spo2 = findSensor(data, "spo2");
  const muscle = findSensor(data, "muscle_density");
  const ph = findSensor(data, "urine_ph");
  const temp = findSensor(data, "urine_temperature");
  const radiation = findSensor(data, "urine_radiation_marker");
  const alerts = healthAlerts(data);
  const doubtfulSample = temp?.status === "alert" && temp.config.range_role === "sample_validity";

  const card = (title: string, organ: string, s: SensorStatus | null, doubtful = false) => (
    <SensorCard
      title={title}
      organ={organ}
      sensor={s}
      ageSeconds={liveAge(s, updatedAt, now)}
      loaded={loaded}
      offline={offline}
      tag={doubtful ? <StatusPill state="doubtful" /> : undefined}
    />
  );

  return (
    <div className="screen">
      {offline ? (
        <ServiceBanner error={error} updatedAt={updatedAt} onRetry={refresh} />
      ) : !loaded ? (
        <div className="banner" role="status">
          <div className="banner__text">
            <span className="banner__title">Loading readings…</span>
            <span>Connecting to the onboard service. This usually takes a few seconds.</span>
          </div>
        </div>
      ) : alerts.length > 0 ? (
        <AlertBanner
          alerts={alerts}
          ageSeconds={liveAge(alerts[0], updatedAt, now)}
          onNavigate={onNavigate}
        />
      ) : (
        <SummaryBanner sensors={[spo2, muscle, heart, ph]} />
      )}
      <div className="estado__grid">
        <div className="estado__col">
          {card("Blood oxygen", "SpO₂ · lungs", spo2)}
          {card("Muscle density", "Limbs", muscle)}
        </div>
        <div className="estado__center">
          <BodyMap
            lungs={loaded ? shownStatus(spo2, offline) : null}
            heart={loaded ? shownStatus(heart, offline) : null}
            kidneys={loaded ? shownStatus(ph, offline) : null}
            limbs={loaded ? shownStatus(muscle, offline) : null}
          />
          {loaded ? (
            // Any radiation reading is "possible exposure": never a dose, never an all-clear.
            <div className={`estado__radiation${radiation?.latest ? " estado__radiation--flag" : ""}`}>
              <StateIcon state={radiation?.latest ? "doubtful" : "no_data"} />
              <span>
                <strong>Radiation:</strong>{" "}
                {radiation?.latest ? "possible exposure, needs confirmation." : "no data."} It is an
                indirect indicator and does not measure dose.
              </span>
            </div>
          ) : null}
        </div>
        <div className="estado__col">
          {card("Heart rate", "Heart", heart)}
          {card("Urine · pH", "Kidneys", ph, doubtfulSample)}
        </div>
      </div>
    </div>
  );
}
