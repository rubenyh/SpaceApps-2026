"""Deliver summaries: print/append in dry-run, otherwise POST with a local JSONL outbox."""

import json
from pathlib import Path

import httpx
from pydantic import BaseModel


class Sink:
    def __init__(
        self,
        api_url: str,
        outbox_path: Path,
        dry_run: bool = False,
        dry_run_file: Path | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.dry_run_file = dry_run_file
        self.outbox_path = outbox_path
        self.client = client or httpx.Client(base_url=api_url, timeout=5.0)

    def send(self, route: str, payload: BaseModel) -> bool:
        """Return True if delivered now (dry-run counts as delivered)."""
        body = payload.model_dump(mode="json")
        if self.dry_run:
            line = json.dumps({"route": route, "body": body}, ensure_ascii=False)
            print(line)
            if self.dry_run_file:
                self.dry_run_file.parent.mkdir(parents=True, exist_ok=True)
                with self.dry_run_file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            return True
        self.flush_outbox()
        if self._post(route, body):
            return True
        self._append(self.outbox_path, route, body)
        return False

    def flush_outbox(self) -> None:
        if not self.outbox_path.exists():
            return
        entries = [
            json.loads(line)
            for line in self.outbox_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        left = [e for e in entries if not self._post(e["route"], e["body"])]
        if left:
            self.outbox_path.write_text(
                "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in left),
                encoding="utf-8",
            )
        else:
            self.outbox_path.unlink()

    def _post(self, route: str, body: dict) -> bool:
        try:
            r = self.client.post(route, json=body)
        except httpx.HTTPError as exc:
            print(f"[sink] {route} unreachable: {exc}")
            return False
        if r.status_code < 300:
            return True
        if 400 <= r.status_code < 500 and r.status_code not in (404, 408, 429):
            # Rejected payload: retrying will not help, so park it instead of looping.
            print(f"[sink] {route} rejected {r.status_code}: {r.text[:300]}")
            self._append(self.outbox_path.with_name("rejected.jsonl"), route, body)
            return True
        print(f"[sink] {route} failed {r.status_code}")
        return False

    @staticmethod
    def _append(path: Path, route: str, body: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"route": route, "body": body}, ensure_ascii=False) + "\n")
