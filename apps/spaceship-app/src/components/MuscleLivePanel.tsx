import { useEffect, useState } from "react";
import { useNow } from "../hooks/useNow";
import type { Point } from "./chartScale";
import { LineChart } from "./LineChart";
import { Panel } from "./Panel";

// Live feed from firmware/muscle_live.py (phone slider). Separate from onboard-api on purpose:
// it is not stored, not sent to ground and not seen by the assistant.
const FEED_URL = (import.meta.env.VITE_MUSCLE_LIVE_URL || "http://127.0.0.1:8765").replace(/\/+$/, "");
const WINDOW_MS = 60_000;

type Feed = "waiting" | "live" | "disconnected";

/** Polls the live feed once per second; retries forever, so it reconnects on its own. */
export function useMuscleFeed() {
  const [points, setPoints] = useState<Point[]>([]);
  const [feed, setFeed] = useState<Feed>("waiting");
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const run = async () => {
      try {
        const res = await fetch(`${FEED_URL}/samples`, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(2000)]),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { samples: { t: number; v: number }[] };
        setPoints(body.samples);
        setFeed(body.samples.length ? "live" : "waiting");
      } catch {
        if (controller.signal.aborted) return;
        setFeed((f) => (f === "waiting" ? "waiting" : "disconnected"));
      }
      if (!controller.signal.aborted) timer = setTimeout(run, 1000);
    };
    void run();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);
  return { points, feed };
}

export function MuscleLivePanel() {
  const { points, feed } = useMuscleFeed();
  const now = useNow(1000);
  const last = feed === "live" ? points[points.length - 1] : undefined;
  // The newest sample can be a moment ahead of the 1 s clock tick: keep it in the window.
  const end = Math.max(now, last?.t ?? 0);

  return (
    <Panel
      title="Live muscle reading"
      aside={<span className="pill pill--no_data">Real time</span>}
    >
      <div className="panel__caption">
        <span className="caption">Value in kg · 1 sample per second · last 60 s · times in UTC</span>
        <span className="caption" role="status">
          {feed === "live" ? "Latest " : feed === "waiting" ? "Waiting for feed · " : "Disconnected · retrying · "}
          <strong className="musculo__live-value">{last ? `${last.v.toFixed(2)} kg` : "---"}</strong>
        </span>
      </div>
      <LineChart
        points={feed === "disconnected" ? [] : points}
        start={end - WINDOW_MS}
        end={end}
        yDomain={[0, 5]}
        width={790}
        height={200}
        label="Live muscle reading"
        emptyText={`${feed === "disconnected" ? "Feed disconnected" : "Waiting for feed"} · run python firmware/muscle_live.py`}
      />
    </Panel>
  );
}

/** Compact latest value for the Status screen's muscle card. */
export function MuscleLiveStat() {
  const { points, feed } = useMuscleFeed();
  const last = feed === "live" ? points[points.length - 1] : undefined;
  return (
    <div className="stats">
      <div className="stat" role="status">
        <span>Live muscle reading</span>
        <strong className="musculo__live-value">
          {last ? `${last.v.toFixed(2)} kg` : feed === "waiting" ? "Waiting…" : "Disconnected"}
        </strong>
      </div>
      <div className="stat">
        <span>Feed</span>
        <strong>{feed === "live" ? "Real time" : "Retrying"}</strong>
      </div>
    </div>
  );
}
