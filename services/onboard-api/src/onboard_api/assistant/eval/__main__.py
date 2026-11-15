"""uv run python -m onboard_api.assistant.eval --cases DIR --out DIR [--baseline result.json]
[--min-hit-rate 0.8] [--candidate-id ID]

Writes manifest.json, result.json and report.md to --out. Exit 1 when release_blocked
(missed alarm or unsafe action) or when the retrieval hit rate is below --min-hit-rate.
"""

import argparse
import json
import sys
from pathlib import Path

from onboard_api.assistant.eval.manifest import build_manifest
from onboard_api.assistant.eval.report import render
from onboard_api.assistant.eval.runner import live_up, run
from onboard_api.config import Settings


def main(argv: list[str] | None = None, up_factory=live_up) -> int:
    parser = argparse.ArgumentParser(prog="python -m onboard_api.assistant.eval")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, help="result.json of the current baseline")
    parser.add_argument("--min-hit-rate", type=float, default=0.8)
    parser.add_argument("--candidate-id")
    args = parser.parse_args(argv)
    if not args.cases.is_dir():
        parser.error(f"--cases {args.cases} is not a directory")

    settings = Settings()
    manifest = build_manifest(args.cases, settings, args.candidate_id)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    result = run(args.cases, manifest, up_factory(settings), baseline)

    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("manifest.json", manifest), ("result.json", result)):
        (args.out / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "report.md").write_text(render(result, baseline), encoding="utf-8")

    s = result["summary"]
    print(f"{s['passed']}/{s['cases']} passed, {s['blocking_failures']} blocking, "
          f"retrieval_hit_rate={s['retrieval_hit_rate']}, citation_support_rate={s['citation_support_rate']}, "
          f"p50={s['latency_ms_p50']} ms, p95={s['latency_ms_p95']} ms -> {args.out}")
    low_hit = s["retrieval_hit_rate"] is not None and s["retrieval_hit_rate"] < args.min_hit_rate
    if low_hit:
        print(f"FAIL: retrieval hit rate below {args.min_hit_rate:.0%}")
    if s["release_blocked"]:
        print("RELEASE BLOCKED: see report.md")
    return 1 if s["release_blocked"] or low_hit else 0


if __name__ == "__main__":
    sys.exit(main())
