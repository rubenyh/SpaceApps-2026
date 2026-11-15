import { getReadings } from "../api/ground";
import type { CrewMember, GroundReading, SensorKind, SensorStatus } from "../api/types";
import { Flap } from "../components/Flap";
import { LineChart, type Point } from "../components/LineChart";
import { RangeLabel, SensorName, Swatch } from "../components/labels";
import { usePolling, type PollState } from "../hooks/usePolling";
import { cellView, freshestAge, liveAge, ROW_LABELS, rowState } from "../lib/board";
import { configRange, formatAge, QUALITY_LABELS, SENSOR_LABELS } from "../lib/format";

interface Props {
  crew: CrewMember[] | null;
  crewAt: number | null;
  offline: boolean;
  now: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const MIN = 60_000;
const VITALS_WINDOW = 15 * MIN;
const DAYS_WINDOW = 14 * 24 * 60 * MIN;
const VITAL_KINDS: SensorKind[] = ["heart_rate", "spo2"];
const DAY_KINDS: SensorKind[] = ["urine_ph", "urine_salinity", "urine_radiation_marker", "muscle_density"];

type Series = Partial<Record<SensorKind, GroundReading[]>>;

function fetchSeries(id: string, kinds: SensorKind[], windowMs: number) {
  return async (signal: AbortSignal): Promise<Series> => {
    const since = new Date(Date.now() - windowMs).toISOString();
    const lists = await Promise.all(kinds.map((kind) => getReadings(id, { kind, since, limit: 1000 }, signal)));
    return Object.fromEntries(kinds.map((k, i) => [k, lists[i]]));
  };
}

const toPoints = (rs: GroundReading[] | undefined): Point[] =>
  (rs ?? [])
    .filter((r) => r.value !== null)
    .map((r) => ({ t: Date.parse(r.recorded_at), v: r.value as number }))
    .sort((a, b) => a.t - b.t);

export function Astronauta({ crew, crewAt, offline, now, selectedId, onSelect }: Props) {
  const member = crew?.find((m) => m.astronaut_id === selectedId) ?? null;
  const id = member?.astronaut_id ?? null;
  const vitals = usePolling(id && `v:${id}`, fetchSeries(id ?? "", VITAL_KINDS, VITALS_WINDOW), 5_000);
  const days = usePolling(id && `d:${id}`, fetchSeries(id ?? "", DAY_KINDS, DAYS_WINDOW), 30_000);

  if (crew === null) {
    return (
      <p className="empty">
        {offline
          ? "No crew data: the ground service is not answering."
          : "Loading crew…"}
      </p>
    );
  }
  if (crew.length === 0 || !member) {
    return (
      <p className="empty">No crew on ground yet. Crew appears with the first batch the ship sends.</p>
    );
  }

  const state = rowState(member.sensors, offline);
  const age = liveAge(freshestAge(member.sensors), crewAt, now);

  return (
    <>
      <div className="toolbar">
        <h1 className="sr-only">Astronaut {member.display_name}</h1>
        <label className="toolbar__label" htmlFor="astro-select">
          Astronaut
        </label>
        <select id="astro-select" value={member.astronaut_id} onChange={(e) => onSelect(e.target.value)}>
          {crew.map((m) => (
            <option key={m.astronaut_id} value={m.astronaut_id}>
              {m.display_name} ({m.astronaut_id})
            </option>
          ))}
        </select>
        <span className={`cell cell--state cell--${state}`}>
          <Flap text={ROW_LABELS[state]} />
        </span>
        <span className="toolbar__meta">
          {age === null ? "No data received" : `Last data ${formatAge(age)} (measured on ground)`}
        </span>
      </div>

      <table className="sensors">
        <caption className="sr-only">Sensors of {member.display_name}</caption>
        <thead>
          <tr>
            <th scope="col">Sensor</th>
            <th scope="col">Value</th>
            <th scope="col">Unit</th>
            <th scope="col">Range</th>
            <th scope="col">Quality</th>
            <th scope="col">Age on ground</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {member.sensors.map((s) => (
            <SensorRow key={s.kind} s={s} offline={offline} age={liveAge(s.age_seconds, crewAt, now)} />
          ))}
        </tbody>
      </table>
      <p className="hint">
        PROV.: provisional demo range, not clinically validated. Radiation marker: urinary 8-OHdG,
        an indirect marker of oxidative DNA damage, never a dose (ISS crew dose: 0.2–0.5 mSv/day).
      </p>

      <section className="section" aria-labelledby="vitals-title">
        <h2 id="vitals-title">Vital signs, last 15 min</h2>
        <div className="charts charts--2">
          {VITAL_KINDS.map((k) => (
            <Trend key={k} kind={k} member={member} poll={vitals} start={now - VITALS_WINDOW} end={now} />
          ))}
        </div>
      </section>

      <section className="section" aria-labelledby="days-title">
        <h2 id="days-title">Urine, radiation marker and muscle, last 14 days</h2>
        <div className="charts charts--3">
          {DAY_KINDS.map((k) => (
            <Trend key={k} kind={k} member={member} poll={days} start={now - DAYS_WINDOW} end={now} points />
          ))}
        </div>
      </section>
    </>
  );
}

function SensorRow({ s, offline, age }: { s: SensorStatus; offline: boolean; age: number | null }) {
  const c = cellView(s, offline);
  const quality = s.latest?.quality;
  return (
    <tr>
      <th scope="row">
        <SensorName kind={s.kind} />
      </th>
      <td className={`cell cell--${c.tone}`}>
        <span className="value">
          {s.kind === "urine_color" ? <Swatch value={s.latest?.value_text} /> : null}
          <Flap text={c.text} tiles={c.text.length <= 8} width={4} />
        </span>
      </td>
      <td>{s.latest?.unit ?? s.config.unit ?? "--"}</td>
      <td><RangeLabel config={s.config} /></td>
      <td className={quality && quality !== "good" ? "quality quality--warn" : "quality"}>
        {quality ? QUALITY_LABELS[quality] : "--"}
      </td>
      <td>{age === null ? <span className="muted">No data</span> : formatAge(age)}</td>
      <td className={`cell cell--${c.tone}`}>
        <Flap text={c.note || "In range"} className="flap--text" />
      </td>
    </tr>
  );
}

interface TrendProps {
  kind: SensorKind;
  member: CrewMember;
  poll: PollState<Series>;
  start: number;
  end: number;
  points?: boolean;
}

function Trend({ kind, member, poll, start, end, points = false }: TrendProps) {
  const config = member.sensors.find((s) => s.kind === kind)?.config;
  const range = config ? configRange(config) : null;
  return (
    <figure className="trend">
      <figcaption>
        <span>
          <SensorName kind={kind} />
          {config?.unit ? <span className="board__unit"> {config.unit}</span> : null}
        </span>
        <span className="trend__range">
          {range ? `Range ${range}` : "No range"}
          {range && config?.provisional ? <span className="tag tag--prov">PROV.</span> : null}
        </span>
      </figcaption>
      {poll.data === null ? (
        poll.error ? (
          <p className="trend__state">
            Trend not available:{" "}
            {poll.error.kind === "network" ? "the ground service is not answering" : poll.error.message}
          </p>
        ) : (
          <div className="trend__skeleton" aria-label="Loading trend" />
        )
      ) : (
        <LineChart
          points={toPoints(poll.data[kind])}
          start={start}
          end={end}
          normalMin={config?.normal_min ?? null}
          normalMax={config?.normal_max ?? null}
          width={points ? 400 : 560}
          cap={kind === "spo2" && config?.unit === "%" ? 100 : null}
          showPoints={points}
          label={SENSOR_LABELS[kind]}
          emptyText="No readings in this period"
        />
      )}
    </figure>
  );
}
