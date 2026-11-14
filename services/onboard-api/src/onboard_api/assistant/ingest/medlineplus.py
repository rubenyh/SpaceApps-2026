"""MedlinePlus Health Topic XML: select manifest topics, strip HTML, chunk.

Only the health-topic `full-summary` is used (MedlinePlus-authored text). Linked
A.D.A.M. encyclopedia pages are never fetched or copied.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

MAX_TOKENS = 300  # plan §5: 150–300 token target per chunk
TINY_TOKENS = 60  # chunks below this merge into the next chunk of the same page
DEFAULT_SECTION = {"es": "Resumen", "en": "Summary"}
_ATTRIBUTION = re.compile(r"^(NIH|NLM|CDC|FDA)\b.{0,120}$")  # trailing "NIH: ..." lines


def estimate_tokens(text: str) -> int:
    # ponytail: word count heuristic (~1.4 tokens/word for es/en with bge-m3's
    # tokenizer); swap for the real tokenizer if chunk sizes ever matter more.
    return int(len(text.split()) * 1.4) + 1


class _BlockParser(HTMLParser):
    """Splits summary HTML into (kind, text) blocks: heading, para or list."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._buf: list[str] = []
        self._kind = "para"
        self._list_depth = 0
        self._strong = 0
        self._plain_text = False  # para has text outside <strong>/<b>
        self._skip = False

    def _flush(self) -> None:
        raw = "".join(self._buf)
        self._buf = []
        if self._kind == "list":
            lines = [" ".join(line.split()) for line in raw.split("\n")]
            text = "\n".join(line for line in lines if line.strip("- "))
        else:
            text = " ".join(raw.split())
        kind = self._kind
        if kind == "para" and text and not self._plain_text:
            kind = "heading"  # <p><strong>Question?</strong></p> is used as a heading
        if text:
            self.blocks.append((kind, text))
        self._kind, self._plain_text = "para", False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "style":
            self._skip = True
        elif tag in ("ul", "ol"):
            if self._list_depth == 0:
                self._flush()
                self._kind = "list"
            self._list_depth += 1
        elif tag == "li":
            self._buf.append("\n- ")
        elif self._list_depth:
            if tag == "br":
                self._buf.append(" ")
        elif tag in ("h2", "h3", "h4"):
            self._flush()
            self._kind = "heading"
        elif tag == "p":
            self._flush()
        elif tag in ("strong", "b"):
            self._strong += 1
        elif tag in ("br", "td", "th"):
            self._buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._skip = False
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            if self._list_depth == 0:
                self._flush()
        elif self._list_depth:
            return
        elif tag in ("h2", "h3", "h4", "p"):
            self._flush()
        elif tag in ("strong", "b"):
            self._strong = max(0, self._strong - 1)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._buf.append(data)
        if self._kind == "para" and self._strong == 0 and data.strip():
            self._plain_text = True

    def close(self) -> None:
        super().close()
        self._flush()


def html_blocks(html: str) -> list[tuple[str, str]]:
    parser = _BlockParser()
    parser.feed(html)
    parser.close()
    blocks = parser.blocks
    while blocks and blocks[-1][0] == "para" and _ATTRIBUTION.match(blocks[-1][1]):
        blocks = blocks[:-1]
    return blocks


def chunk_summary(html: str, language: str) -> list[tuple[str, str]]:
    """Return (section, text) chunks: one idea and one language per chunk.

    A short summary stays whole. Longer ones split at headings, then pack
    paragraphs/lists up to MAX_TOKENS (a list is never split, and a paragraph
    ending in ':' stays with what follows). Tiny chunks merge forward.
    """
    blocks = html_blocks(html)
    if not blocks:
        return []
    default = DEFAULT_SECTION[language]
    whole = "\n\n".join(text for _, text in blocks)
    if estimate_tokens(whole) <= MAX_TOKENS:
        return [(default, whole)]

    chunks: list[tuple[str, str]] = []
    section, current = default, []

    def flush() -> None:
        if current:
            chunks.append((section, "\n\n".join(current)))
            current.clear()

    for kind, text in blocks:
        if kind == "heading":
            flush()
            section = text
            continue
        candidate = "\n\n".join([*current, text])
        if current and estimate_tokens(candidate) > MAX_TOKENS:
            # A lead-in paragraph ending in ':' moves with the list it introduces.
            carry = [current.pop()] if current[-1].endswith(":") else []
            flush()
            current.extend(carry)
        current.append(text)
    flush()

    merged: list[tuple[str, str]] = []
    pending: tuple[str, str] | None = None
    for sec, text in chunks:
        if pending:
            joined = f"{pending[1]}\n\n{text}"
            if estimate_tokens(joined) <= MAX_TOKENS:
                label = sec if pending[0] == sec else f"{pending[0]} / {sec}"
                sec, text = label, joined
            else:
                merged.append(pending)
            pending = None
        if estimate_tokens(text) < TINY_TOKENS:
            pending = (sec, text)
        else:
            merged.append((sec, text))
    if pending:  # trailing tiny chunk: merge backward when it fits
        if merged and estimate_tokens(f"{merged[-1][1]}\n\n{pending[1]}") <= MAX_TOKENS:
            sec, text = merged.pop()
            label = sec if sec == pending[0] else f"{sec} / {pending[0]}"
            pending = (label, f"{text}\n\n{pending[1]}")
        merged.append(pending)
    return merged


def xml_version(root: ET.Element) -> str:
    """ISO date of the XML from `date-generated` ("11/13/2026 08:58:25")."""
    stamp = root.get("date-generated", "").split(" ")[0]
    return datetime.strptime(stamp, "%m/%d/%Y").date().isoformat()


def load_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def build_chunks(
    root: ET.Element, topics: list[dict[str, str]], reuse_basis: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Chunks for each manifest topic (English + mapped Spanish). Returns (chunks, problems)."""
    version = xml_version(root)
    by_url = {t.get("url"): t for t in root.iter("health-topic")}
    chunks: list[dict[str, Any]] = []
    problems: list[str] = []
    for entry in topics:
        english = by_url.get(entry["english_url"])
        if english is None or english.get("language") != "English":
            problems.append(f"{entry['source_id']}: English topic not found in XML")
            continue
        records = [("en", english)]
        mapped = english.find("language-mapped-topic[@language='Spanish']")
        spanish = by_url.get(mapped.get("url")) if mapped is not None else None
        if spanish is None:
            problems.append(f"{entry['source_id']}: no Spanish equivalent in XML")
        else:
            records.append(("es", spanish))
        for language, record in records:
            parts = chunk_summary(record.findtext("full-summary") or "", language)
            if not parts:
                problems.append(f"{entry['source_id']}/{language}: empty summary")
            for index, (section, text) in enumerate(parts, start=1):
                chunks.append(
                    {
                        "chunk_id": f"{entry['source_id']}-{language}-{index:02d}",
                        "source_id": entry["source_id"],
                        "source_title": record.get("title"),
                        "source_url": record.get("url"),
                        "section": section,
                        "topic": entry["topic"],
                        "language": language,
                        "source_version": version,
                        "reuse_basis": reuse_basis,
                        "text": text,
                    }
                )
    return chunks, problems
