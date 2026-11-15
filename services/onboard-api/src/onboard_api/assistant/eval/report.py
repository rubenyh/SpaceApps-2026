"""Side-by-side Markdown report: candidate vs baseline, per case and summary."""

SUMMARY_KEYS = ("cases", "passed", "failed", "blocking_failures", "release_blocked", "retrieval_hit_rate",
                "citation_support_rate", "latency_ms_p50", "latency_ms_p95")


def _cell(value) -> str:
    return "-" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def _brief(r: dict | None) -> str:
    if r is None:
        return "-"
    return _cell(f"{r['workflow']} / {r['urgency']} / {r['protocol_id']}")


def render(result: dict, baseline: dict | None = None) -> str:
    m, b = result["manifest"], result["baseline"]
    lines = [
        "# Medical evaluation report",
        "",
        f"Candidate `{m['candidate_id']}` (digest `{m['digest'][:12]}`), run {result['run_at']}.",
        f"Baseline: `{b['candidate_id']}` (digest `{b['digest'][:12]}`)." if b else "Baseline: none.",
        "",
        "**RELEASE BLOCKED**: missed alarm or unsafe action in at least one case."
        if result["summary"]["release_blocked"] else "No blocking failures.",
        "",
        "## Summary",
        "",
        "| Metric | Candidate | Baseline |",
        "|---|---|---|",
    ]
    base_summary = (baseline or {}).get("summary", {})
    lines += [f"| {k} | {_cell(result['summary'].get(k))} | {_cell(base_summary.get(k))} |" for k in SUMMARY_KEYS]
    base_cases = {c["case_id"]: c for c in (baseline or {}).get("cases", [])}
    lines += [
        "",
        "## Cases",
        "",
        "Response = workflow / urgency / protocol_id.",
        "",
        "| Case | Family | Review | Candidate | Result | Baseline | Baseline result | Changed | Failures |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    # Blocking first, then failed, then passed.
    for c in sorted(result["cases"], key=lambda c: (not c["blocking"], c["passed"], str(c["case_id"]))):
        bc = base_cases.get(c["case_id"])
        status = "BLOCKING" if c["blocking"] else "pass" if c["passed"] else "fail"
        base_status = "-" if bc is None else "pass" if bc["passed"] else "fail"
        cand, base = _brief(c["response"]), _brief(c["baseline_response"])
        changed = "-" if c["baseline_response"] is None else "yes" if cand != base else "no"
        failures = "; ".join(f"{f['code']}: {f['detail']}" for f in c["failures"])
        lines.append(f"| {_cell(c['case_id'])} | {_cell(c['family'])} | {_cell(c['review_status'])} | {cand} "
                     f"| {status} | {base} | {base_status} | {changed} | {_cell(failures or None)} |")
    return "\n".join(lines) + "\n"
