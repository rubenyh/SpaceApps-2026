import type { CrewMember, Link, SensorKind } from "../api/types";
import { Flap, FlapSkeleton } from "../components/Flap";
import { SensorName } from "../components/labels";
import { Ledger } from "../components/Ledger";
import {
  BOARD_KINDS,
  cellView,
  freshestAge,
  liveAge,
  ROW_LABELS,
  rowState,
  type LedgerEntry,
} from "../lib/board";
import { formatAge } from "../lib/format";

interface Props {
  crew: CrewMember[] | null;
  crewAt: number | null;
  offline: boolean;
  now: number;
  link: Link | null;
  ledger: LedgerEntry[];
  onOpen: (astronautId: string) => void;
}

const COLS = BOARD_KINDS.length + 3;
// Fixed character cells per column, like a departures board. Longer values add tiles.
const TILES: Partial<Record<SensorKind, number>> = {
  heart_rate: 3,
  spo2: 3,
  urine_ph: 3,
  urine_salinity: 4,
  muscle_density: 4,
};

export function Tripulacion({ crew, crewAt, offline, now, link, ledger, onOpen }: Props) {
  const units = crew?.[0]?.sensors;
  const configOf = (kind: string) => units?.find((s) => s.kind === kind)?.config;
  const unitOf = (kind: string) => configOf(kind)?.unit ?? null;
  const noRange = (kind: string) => {
    const c = configOf(kind);
    return !!c && c.normal_min === null && c.normal_max === null;
  };

  return (
    <>
      <h1 className="sr-only">Crew</h1>
      <div className="board-wrap">
        <table className="board">
          <caption className="sr-only">
            Crew board: one astronaut per row. Open an astronaut to see the details.
          </caption>
          <thead>
            <tr>
              <th scope="col">Astronaut</th>
              {BOARD_KINDS.map((k) => (
                <th scope="col" key={k}>
                  <SensorName kind={k} />
                  {unitOf(k) ? <span className="board__unit"> {unitOf(k)}</span> : null}
                  {noRange(k) ? <span className="board__norange">No range</span> : null}
                </th>
              ))}
              <th scope="col">Status</th>
              <th scope="col">Last data</th>
            </tr>
          </thead>
          <tbody>
            {crew === null ? (
              offline ? (
                <tr>
                  <td colSpan={COLS} className="board__empty">
                    No crew data: the ground service is not answering. Crew data appears as soon as it
                    answers.
                  </td>
                </tr>
              ) : (
                [0, 1].map((i) => (
                  <tr key={i} className="row row--skeleton" aria-hidden="true">
                    <th scope="row">
                      <FlapSkeleton tiles={8} />
                    </th>
                    {BOARD_KINDS.map((k) => (
                      <td key={k}>
                        <FlapSkeleton tiles={TILES[k]} />
                      </td>
                    ))}
                    <td>
                      <FlapSkeleton tiles={6} />
                    </td>
                    <td>
                      <FlapSkeleton tiles={4} />
                    </td>
                  </tr>
                ))
              )
            ) : crew.length === 0 ? (
              <tr>
                <td colSpan={COLS} className="board__empty">
                  {link?.last_batch_received_at
                    ? "The batches received carry no crew."
                    : "No crew on ground yet. Crew appears with the first batch the ship sends."}
                </td>
              </tr>
            ) : (
              crew.map((m) => {
                const state = rowState(m.sensors, offline);
                const age = liveAge(freshestAge(m.sensors), crewAt, now);
                return (
                  <tr key={m.astronaut_id} className={`row row--${state}`} onClick={() => onOpen(m.astronaut_id)}>
                    <th scope="row">
                      <button
                        type="button"
                        className="row__open"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpen(m.astronaut_id);
                        }}
                        aria-label={`Open ${m.display_name}`}
                      >
                        <Flap text={m.display_name} />
                      </button>
                    </th>
                    {BOARD_KINDS.map((k) => {
                      const c = cellView(
                        m.sensors.find((s) => s.kind === k),
                        offline,
                      );
                      return (
                        <td key={k} className={`cell cell--${c.tone}`}>
                          <Flap text={c.text} tiles width={TILES[k]} />
                          {/* "No range" is stated once in the column header. */}
                          <span className="note">{c.note === "No range" ? "" : c.note}</span>
                        </td>
                      );
                    })}
                    <td className={`cell cell--state cell--${state}`}>
                      <Flap text={ROW_LABELS[state]} />
                    </td>
                    <td className="cell cell--age">
                      <Flap text={age === null ? "Never" : formatAge(age)} animate={false} />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <section className="section" aria-labelledby="ledger-title">
        <h2 id="ledger-title">Batches received</h2>
        <Ledger ledger={ledger} link={link} offline={offline} />
      </section>
    </>
  );
}
