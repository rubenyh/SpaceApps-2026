import { useEffect, useState, type FormEvent } from "react";
import { toApiError } from "../api/client";
import { getCandidate, getCandidates, getDraftCase, postDecision, postFinding } from "../api/ground";
import type {
  CandidateDetail,
  DecisionKind,
  EvalCaseResult,
  EvalFinding,
  EvalResponse,
  EvalSource,
  FindingKind,
  ReviewRole,
} from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { utcFull } from "../lib/incidents";
import {
  approveBlockedReason,
  approveButtonLabel,
  decisionLabel,
  draftFileName,
  FINDING_KINDS,
  findingKindLabel,
  findingsByCase,
  percent,
  shortDigest,
  sortCases,
  statusLabel,
} from "../lib/medicalEval";

const LIST_POLL_MS = 10_000;
const DETAIL_POLL_MS = 10_000;

const errorText = (err: unknown) => {
  const e = toApiError(err);
  return e.kind === "network" ? "Ground service unreachable." : `Ground service error (${e.message}).`;
};

function Sources({ sources }: { sources: EvalSource[] }) {
  if (!sources.length) return <p className="muted">No sources cited.</p>;
  return (
    <ul className="eval-sources">
      {sources.map((s) => (
        <li key={s.id}>
          {s.title ?? s.id}
          {s.section ? ` · ${s.section}` : ""} <span className="muted">({s.id})</span>
        </li>
      ))}
    </ul>
  );
}

function Answer({ title, response, empty }: { title: string; response: EvalResponse | null; empty: string }) {
  return (
    <div className="eval-answer">
      <h3>{title}</h3>
      {response === null ? (
        <p className="muted">{empty}</p>
      ) : (
        <>
          <p className="hint">
            Workflow {response.workflow} · Urgency {response.urgency ?? "none"} · Protocol {response.protocol_id ?? "none"}
          </p>
          <p className="eval-reply">{response.reply}</p>
          <p>
            <strong>Action:</strong> {response.action ?? <span className="muted">none</span>}
          </p>
          <Sources sources={response.sources} />
        </>
      )}
    </div>
  );
}

function FlagForm({ digest, caseId, onDone }: { digest: string; caseId: string; onDone: () => void }) {
  const [kind, setKind] = useState<FindingKind>("warning_sign");
  const [whenItApplies, setWhen] = useState("");
  const [source, setSource] = useState("");
  const [expected, setExpected] = useState("");
  const [reporter, setReporter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postFinding(digest, {
        case_id: caseId,
        kind,
        when_it_applies: whenItApplies.trim(),
        source: source.trim(),
        expected_behavior: expected.trim(),
        reporter: reporter.trim(),
      });
      onDone();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  };

  return (
    <form className="eval-form" onSubmit={submit}>
      <label>
        Missing
        <select value={kind} onChange={(e) => setKind(e.target.value as FindingKind)}>
          {FINDING_KINDS.map((k) => (
            <option key={k.key} value={k.key}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        When it applies
        <textarea required value={whenItApplies} onChange={(e) => setWhen(e.target.value)} rows={2} />
      </label>
      <label>
        Supporting source
        <input required value={source} onChange={(e) => setSource(e.target.value)} />
      </label>
      <label>
        Expected behaviour
        <textarea required value={expected} onChange={(e) => setExpected(e.target.value)} rows={2} />
      </label>
      <label>
        Reporter
        <input required value={reporter} onChange={(e) => setReporter(e.target.value)} />
      </label>
      {error ? <p role="alert" className="eval-error">{error}</p> : null}
      <div className="eval-actions">
        <button type="submit" className="button" disabled={busy}>
          {busy ? "Sending…" : "Send finding"}
        </button>
        <button type="button" className="button" onClick={onDone} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Finding({ finding: f }: { finding: EvalFinding }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      setDraft(JSON.stringify(await getDraftCase(f.id), null, 2));
    } catch (err) {
      setError(errorText(err));
    }
  };

  const download = () => {
    if (draft === null) return;
    const url = URL.createObjectURL(new Blob([draft + "\n"], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = draftFileName(f.case_id, f.id);
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <li className="eval-finding">
      <p>
        <span className="tag tag--prov">{findingKindLabel(f.kind)}</span>
        <span className="tag tag--prov">{f.status}</span> {f.expected_behavior}
      </p>
      <p className="hint">
        When: {f.when_it_applies} · Source: {f.source} · By {f.reporter} · {utcFull(f.created_at)} · Version{" "}
        {shortDigest(f.digest)}
      </p>
      <div className="eval-actions">
        <button type="button" className="button" onClick={load}>
          Draft regression test
        </button>
        {draft !== null ? (
          <button type="button" className="button" onClick={download}>
            Download JSON
          </button>
        ) : null}
      </div>
      {error ? <p role="alert" className="eval-error">{error}</p> : null}
      {draft !== null ? <pre className="eval-json">{draft}</pre> : null}
    </li>
  );
}

function Case({
  c,
  digest,
  findings,
  hasBaseline,
  onChanged,
}: {
  c: EvalCaseResult;
  digest: string;
  findings: EvalFinding[];
  hasBaseline: boolean;
  onChanged: () => void;
}) {
  const [flagging, setFlagging] = useState(false);
  return (
    <section className="section eval-case" aria-labelledby={`case-${c.case_id}`}>
      <h2 id={`case-${c.case_id}`}>
        {c.case_id}
        <span className={c.passed ? "tag tag--prov" : "tag tag--alert"}>
          {c.passed ? "Passed" : c.blocking ? "Failed · blocking" : "Failed"}
        </span>
        <span className="tag tag--prov">Case {c.review_status}</span>
      </h2>
      <p className="hint">
        Family {c.family} · Latency {c.latency_ms} ms
      </p>
      {c.failures.length ? (
        <ul className="eval-failures">
          {c.failures.map((f, i) => (
            <li key={i}>
              <strong>{f.code}</strong>: {f.detail}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="eval-compare">
        <Answer
          title="Before (baseline)"
          response={c.baseline_response}
          empty={hasBaseline ? "No baseline answer for this case." : "No baseline was evaluated."}
        />
        <Answer title="After (this version)" response={c.response} empty="No answer recorded." />
      </div>
      {findings.length ? (
        <>
          <h3 className="eval-subhead">Findings</h3>
          <ul className="eval-findings">
            {findings.map((f) => (
              <Finding key={f.id} finding={f} />
            ))}
          </ul>
        </>
      ) : null}
      {flagging ? (
        <FlagForm
          digest={digest}
          caseId={c.case_id}
          onDone={() => {
            setFlagging(false);
            onChanged();
          }}
        />
      ) : (
        <button type="button" className="button eval-flag" onClick={() => setFlagging(true)}>
          Flag missing scenario
        </button>
      )}
    </section>
  );
}

function Decide({ detail, onChanged }: { detail: CandidateDetail; onChanged: () => void }) {
  const [reviewer, setReviewer] = useState("");
  const [role, setRole] = useState<ReviewRole>("simulated");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const digest = detail.manifest.digest;
  const blocked = approveBlockedReason(detail.status, detail.result.summary.release_blocked);
  const decided = detail.status !== "pending_review";

  const send = async (decision: DecisionKind) => {
    if (!reviewer.trim()) {
      setError("Enter the reviewer name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await postDecision(digest, { decision, reviewer: reviewer.trim(), role, notes: notes.trim() });
      onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="section" aria-labelledby="eval-decide">
      <h2 id="eval-decide">Decision for version {shortDigest(digest)}</h2>
      {detail.decisions.length ? (
        <ul className="eval-decisions">
          {detail.decisions.map((d, i) => (
            <li key={i}>
              <strong>{decisionLabel(d)}</strong> · {d.reviewer}
              {d.notes ? ` · ${d.notes}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {decided ? null : (
        <div className="eval-form">
          <label>
            Reviewer
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value as ReviewRole)}>
              <option value="clinician">Clinician</option>
              <option value="simulated">Simulated (no clinician, hackathon)</option>
            </select>
          </label>
          <label>
            Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </label>
          {blocked ? <p className="eval-error">{blocked}</p> : null}
          {error ? <p role="alert" className="eval-error">{error}</p> : null}
          <div className="eval-actions">
            <button type="button" className="button" disabled={busy || blocked !== null} onClick={() => send("approved")}>
              {approveButtonLabel(role)}
            </button>
            <button type="button" className="button" disabled={busy} onClick={() => send("rejected")}>
              Reject this version
            </button>
          </div>
          <p className="hint">The decision binds to digest {digest} only. Any change to the knowledge bundle needs a new review.</p>
        </div>
      )}
    </section>
  );
}

function Candidate({ digest }: { digest: string }) {
  const { data, error, refresh } = usePolling(`eval-${digest}`, (s) => getCandidate(digest, s), DETAIL_POLL_MS);
  const [failedOnly, setFailedOnly] = useState(false);

  if (!data) {
    return <p className="empty" role={error ? "alert" : undefined}>{error ? errorText(error) : "Loading version…"}</p>;
  }
  const { manifest, result, status } = data;
  const s = result.summary;
  const byCase = findingsByCase(data.findings);
  const cases = sortCases(result.cases).filter((c) => !failedOnly || !c.passed);

  return (
    <>
      {error ? (
        <p className="empty" role="alert">
          {errorText(error)} Showing the last data received; retrying automatically.
        </p>
      ) : null}
      <section className="section" aria-labelledby="eval-version">
        <h2 id="eval-version">
          Version {manifest.candidate_id}
          <span className={s.release_blocked ? "tag tag--alert" : "tag tag--prov"}>
            {s.release_blocked ? "Release blocked" : "Not blocked"}
          </span>
        </h2>
        <dl className="facts eval-facts">
          <div>
            <dt>Status</dt>
            <dd>{statusLabel(status, data.decisions)}</dd>
          </div>
          <div>
            <dt>Digest</dt>
            <dd title={manifest.digest}>{shortDigest(manifest.digest)}</dd>
          </div>
          <div>
            <dt>Baseline</dt>
            <dd>
              {result.baseline ? `${result.baseline.candidate_id} · ${shortDigest(result.baseline.digest)}` : <span className="muted">None</span>}
            </dd>
          </div>
          <div>
            <dt>Run at</dt>
            <dd>{utcFull(result.run_at)}</dd>
          </div>
          <div>
            <dt>Cases</dt>
            <dd>
              {s.cases} · {s.passed} passed · {s.failed} failed
            </dd>
          </div>
          <div>
            <dt>Blocking failures</dt>
            <dd className={s.blocking_failures ? "eval-bad" : undefined}>{s.blocking_failures}</dd>
          </div>
          <div>
            <dt>Retrieval hit rate</dt>
            <dd>{percent(s.retrieval_hit_rate)}</dd>
          </div>
          <div>
            <dt>Citation support</dt>
            <dd>{percent(s.citation_support_rate)}</dd>
          </div>
          <div>
            <dt>Latency p50 / p95</dt>
            <dd>
              {s.latency_ms_p50} ms / {s.latency_ms_p95} ms
            </dd>
          </div>
        </dl>
        <p className="hint">
          Components: {manifest.components.map((c) => `${c.kind} ${shortDigest(c.sha256)}`).join(" · ") || "--"}
        </p>
      </section>

      <Decide detail={data} onChanged={refresh} />

      <div className="toolbar eval-toolbar">
        <label className="toolbar__label">
          <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} /> Failed cases only
        </label>
        <span className="toolbar__meta">
          {cases.length} of {result.cases.length} cases · failed first
        </span>
      </div>
      {cases.map((c) => (
        <Case
          key={c.case_id}
          c={c}
          digest={manifest.digest}
          findings={byCase.get(c.case_id) ?? []}
          hasBaseline={result.baseline !== null}
          onChanged={refresh}
        />
      ))}
    </>
  );
}

/** Review an evaluated knowledge version and approve or reject that exact digest. */
export function MedicalEval() {
  const { data, error } = usePolling("eval-candidates", getCandidates, LIST_POLL_MS);
  const [digest, setDigest] = useState<string | null>(null);

  // Default to the first version waiting for review; recover if the selection disappears.
  useEffect(() => {
    if (!data?.length || data.some((c) => c.digest === digest)) return;
    setDigest((data.find((c) => c.status === "pending_review") ?? data[0]).digest);
  }, [data, digest]);

  return (
    <>
      <h1 className="sr-only">Medical evaluation</h1>
      <p className="hint">
        Automated test results for a candidate medical knowledge version (protocols, rules, guides, model settings).
        Informational support only: the tests do not replace review by qualified medical personnel.
      </p>
      {error ? (
        <p className="empty" role="alert">
          {errorText(error)} Retrying automatically.
        </p>
      ) : null}
      {data === null && !error ? <p className="empty">Loading versions…</p> : null}
      {data?.length === 0 ? <p className="empty">No evaluated versions have reached ground.</p> : null}
      {data?.length ? (
        <div className="toolbar eval-pick">
          <label className="toolbar__label" htmlFor="eval-candidate">
            Version
          </label>
          <select id="eval-candidate" value={digest ?? ""} onChange={(e) => setDigest(e.target.value)}>
            {data.map((c) => (
              <option key={c.digest} value={c.digest}>
                {c.candidate_id} · {shortDigest(c.digest)} · {statusLabel(c.status, null)} · {c.summary.failed} failed
                {c.summary.release_blocked ? " · blocked" : ""}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {digest ? <Candidate key={digest} digest={digest} /> : null}
    </>
  );
}
