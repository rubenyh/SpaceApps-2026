import type { ReactNode } from "react";
import { HttpError } from "../api/client";
import type { SensorKind, SensorStatus } from "../api/types";
import { getAstronautStatus } from "../api/status";
import { BodyMap } from "../components/BodyMap";
import { RangeTrack } from "../components/RangeTrack";
import { ReadingCard } from "../components/ReadingCard";
import { StateIcon, StatusPill } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { TRACK_SCALE, explain, healthAlerts, rangeSide, shownStatus } from "../lib/estado";
import { formatAge, formatUtcDateTime, rangeText, readingValueText, unitLabel } from "../lib/format";
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
  heart_rate: { name: "tu pulso", tab: "vitales", link: "Ver signos vitales" },
  spo2: { name: "tu oxígeno en sangre", tab: "vitales", link: "Ver signos vitales" },
  muscle_density: { name: "el valor de densidad muscular", tab: "musculo", link: "Ver músculo" },
  urine_ph: { name: "el pH de tu orina", tab: "orina", link: "Ver orina" },
  urine_salinity: { name: "el valor de salinidad de tu orina", tab: "orina", link: "Ver orina" },
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
  const how = side === "high" ? "está alto" : side === "low" ? "está bajo" : "está fuera de lo normal";
  const where =
    side === "high" ? "por encima de lo normal" : side === "low" ? "por debajo de lo normal" : "fuera de lo normal";
  const range = rangeText(first.config);
  const unit = unitLabel(first.latest?.unit);
  const others = alerts.length - 1;
  return (
    <div className="estado-banner estado-banner--alert" role="alert">
      <StateIcon state="alert" size={30} pulse />
      <div className="estado-banner__text">
        <span className="estado-banner__title">
          Necesita tu atención: {copy?.name ?? "una lectura"} {how}
        </span>
        <span>
          {readingValueText(first.latest)}
          {unit ? ` ${unit}` : ""}, {where}
          {range ? ` (${range}${first.config.provisional ? ", provisional" : ""})` : ""}.
          {ageSeconds !== null ? ` Medido ${formatAge(ageSeconds)}.` : ""}
          {others > 0 ? ` Hay ${others} ${others === 1 ? "alerta más" : "alertas más"} abajo.` : ""}
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
    count("stale") > 0 ? `${count("stale")} con dato viejo` : "",
    count("no_data") > 0 ? `${count("no_data")} sin datos` : "",
    count("no_range") > 0 ? `${count("no_range")} sin rango` : "",
  ].filter(Boolean);
  return (
    <div className="estado-banner" role="status">
      <StateIcon state={notes.length > 0 ? "no_range" : "normal"} size={30} />
      <div className="estado-banner__text">
        <span className="estado-banner__title">Sin alertas activas</span>
        <span>
          {notes.length > 0
            ? `De estas 4 lecturas: ${notes.join(", ")}. Esas no se pueden evaluar.`
            : "Las 4 lecturas están dentro de lo normal."}
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

  const card = (title: string, organ: string, s: SensorStatus | null, tag?: ReactNode) => {
    if (!loaded) return <section className="card card--skeleton" aria-hidden="true" />;
    const status = shownStatus(s, offline);
    const scale = s ? TRACK_SCALE[s.kind] : undefined;
    const hasRange = s !== null && rangeText(s.config) !== null;
    return (
      <ReadingCard
        title={title}
        organ={organ}
        status={status}
        value={readingValueText(s?.latest)}
        unit={unitLabel(s?.latest?.unit)}
        ageSeconds={liveAge(s, updatedAt, now)}
        quality={s?.latest?.quality}
        explanation={explain(s, offline)}
        tag={tag}
      >
        {s && scale && hasRange ? (
          <RangeTrack value={s.latest?.value ?? null} scale={scale} config={s.config} status={status} />
        ) : (
          <span className="card__note">
            Aún no hay un rango de referencia definido.
          </span>
        )}
      </ReadingCard>
    );
  };

  return (
    <div className="estado">
      {offline ? (
        <div className="estado-banner estado-banner--error" role="alert">
          <StateIcon state="alert" size={30} />
          <div className="estado-banner__text">
            <span className="estado-banner__title">
              {error instanceof HttpError
                ? `Error ${error.status}: ${error.detail}`
                : "SERVICIO ONBOARD NO DISPONIBLE"}
            </span>
            <span>
              {updatedAt !== null
                ? `No llegan lecturas nuevas desde ${formatUtcDateTime(new Date(updatedAt).toISOString())} UTC. Abajo ves los últimos valores recibidos. `
                : "Todavía no se ha recibido ninguna lectura. "}
              Se reintenta cada {POLL_MS / 1000} s.
            </span>
          </div>
          <button type="button" className="btn" onClick={refresh}>
            Reintentar ahora
          </button>
        </div>
      ) : !loaded ? (
        <div className="estado-banner" role="status">
          <div className="estado-banner__text">
            <span className="estado-banner__title">Cargando lecturas…</span>
            <span>Conectando con el servicio de a bordo. Suele tardar unos segundos.</span>
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
          {card("Oxígeno en sangre", "SpO₂ · pulmones", spo2)}
          {card("Densidad muscular", "Extremidades", muscle)}
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
                <strong>Radiación:</strong>{" "}
                {radiation?.latest ? "posible exposición, requiere confirmación." : "sin datos."} Es un
                indicador indirecto, no mide dosis.
              </span>
            </div>
          ) : null}
        </div>
        <div className="estado__col">
          {card("Pulso", "Corazón", heart)}
          {card("Orina · pH", "Riñones", ph, doubtfulSample ? <StatusPill state="doubtful" /> : undefined)}
        </div>
      </div>
    </div>
  );
}
