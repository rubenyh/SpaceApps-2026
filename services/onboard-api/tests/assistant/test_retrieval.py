import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from onboard_api.assistant.ingest.medlineplus import (
    MAX_TOKENS,
    build_chunks,
    chunk_summary,
    estimate_tokens,
)
from onboard_api.assistant.integrations import DependencyUnavailable
from onboard_api.assistant.integrations.chroma import GuideRetriever

VOCAB = ["dolor", "pecho", "fiebre", "chest", "pain", "burns"]


class KeywordEmbedder:
    """Deterministic fake: counts of VOCAB words, plus an 'other' dim when none match."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            words = re.findall(r"\w+", text.lower())
            counts = [float(words.count(w)) for w in VOCAB]
            vectors.append([*counts, 0.0 if any(counts) else 1.0])
        return vectors


def chunk(chunk_id, title, topic, language, text):
    return {
        "chunk_id": chunk_id,
        "source_id": chunk_id.rsplit("-", 2)[0],
        "source_title": title,
        "source_url": f"https://example.org/{chunk_id}",
        "section": "Resumen" if language == "es" else "Summary",
        "topic": topic,
        "language": language,
        "source_version": "2026-11-13",
        "reuse_basis": "test",
        "text": text,
    }


CHUNKS = [
    chunk("mp-chestpain-es-01", "Dolor de pecho", "chest_pain", "es", "dolor pecho presión"),
    chunk("mp-chestpain-en-01", "Chest pain", "chest_pain", "en", "chest pain pressure"),
    chunk("mp-fever-es-01", "Fiebre", "fever", "es", "fiebre temperatura"),
    chunk("mp-burns-en-01", "Burns", "burns", "en", "burns skin"),
]


@pytest.fixture
def retriever(tmp_path: Path) -> GuideRetriever:
    r = GuideRetriever(tmp_path / "chroma", "medical_guides", KeywordEmbedder(), 0.6)
    r.upsert_chunks(CHUNKS, embed_model="fake@0")
    return r


def test_matching_query_hits_best_first(retriever: GuideRetriever) -> None:
    hits = retriever.search("¿Qué causa el dolor de pecho?", language="es")
    assert hits[0].chunk_id == "mp-chestpain-es-01"
    assert hits[0].source_id == "mp-chestpain"
    assert hits[0].title == "Dolor de pecho"
    assert hits[0].url == "https://example.org/mp-chestpain-es-01"
    assert hits[0].text == "dolor pecho presión"
    assert all(h.language == "es" for h in hits)
    assert [h.distance for h in hits] == sorted(h.distance for h in hits)


def test_unrelated_query_returns_empty(retriever: GuideRetriever) -> None:
    assert retriever.search("reiniciar el panel solar") == []


def test_falls_back_to_other_language(retriever: GuideRetriever) -> None:
    hits = retriever.search("burns", language="es")
    assert [h.chunk_id for h in hits] == ["mp-burns-en-01"]


def test_topic_filter(retriever: GuideRetriever) -> None:
    hits = retriever.search("dolor de pecho y fiebre", topics=["fever"], language="es")
    assert [h.topic for h in hits] == ["fever"]


def test_reupsert_is_idempotent_and_delete_missing(retriever: GuideRetriever) -> None:
    retriever.upsert_chunks(CHUNKS[:3])
    assert sum(retriever.count_by("language").values()) == 4
    deleted = retriever.delete_missing(c["chunk_id"] for c in CHUNKS[:3])
    assert deleted == ["mp-burns-en-01"]
    assert retriever.search("burns", language="es") == []


def test_chroma_failure_is_dependency_unavailable(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("x")
    r = GuideRetriever(not_a_dir, "medical_guides", KeywordEmbedder(), 0.6)
    with pytest.raises(DependencyUnavailable):
        r.search("dolor de pecho")


def test_concurrent_first_use_opens_one_client(tmp_path: Path, monkeypatch) -> None:
    import threading
    import time

    import chromadb

    opened = []

    class SlowClient:
        def __init__(self, path):
            opened.append(path)
            time.sleep(0.05)

        def get_or_create_collection(self, *args, **kwargs):
            return object()

    monkeypatch.setattr(chromadb, "PersistentClient", SlowClient)
    r = GuideRetriever(tmp_path / "chroma", "medical_guides", KeywordEmbedder(), 0.6)
    threads = [threading.Thread(target=r._get_collection) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(opened) == 1


# MedlinePlus XML parsing and chunking -------------------------------------------

XML = """<?xml version="1.0" encoding="UTF-8"?>
<health-topics total="3" date-generated="11/13/2026 08:58:25">
<health-topic title="Fainting" url="https://medlineplus.gov/fainting.html" id="1" language="English">
<full-summary>&lt;h3&gt;What is fainting?&lt;/h3&gt;&lt;p&gt;Fainting is a &lt;a href="x"&gt;temporary&lt;/a&gt; loss of consciousness.&lt;/p&gt;
&lt;p&gt;&lt;strong&gt;When to get help?&lt;/strong&gt;&lt;/p&gt;&lt;p&gt;Get help if:&lt;/p&gt;&lt;ul&gt;&lt;li&gt;It happens again&lt;/li&gt;&lt;li&gt;You are injured&lt;/li&gt;&lt;/ul&gt;
&lt;p class=""&gt;NIH: National Heart, Lung, and Blood Institute&lt;/p&gt;</full-summary>
<language-mapped-topic url="https://medlineplus.gov/spanish/fainting.html" id="2" language="Spanish">Desmayos</language-mapped-topic>
</health-topic>
<health-topic title="Desmayos" url="https://medlineplus.gov/spanish/fainting.html" id="2" language="Spanish">
<full-summary>&lt;p&gt;El desmayo es una pérdida temporal&amp;nbsp;del conocimiento.&lt;/p&gt;</full-summary>
<language-mapped-topic url="https://medlineplus.gov/fainting.html" id="1" language="English">Fainting</language-mapped-topic>
</health-topic>
<health-topic title="Burns" url="https://medlineplus.gov/burns.html" id="3" language="English">
<full-summary>&lt;p&gt;Burns damage skin.&lt;/p&gt;</full-summary>
</health-topic>
</health-topics>"""

TOPICS = [
    {"source_id": "medlineplus-fainting", "english_url": "https://medlineplus.gov/fainting.html", "topic": "fainting"},
    {"source_id": "medlineplus-burns", "english_url": "https://medlineplus.gov/burns.html", "topic": "burns"},
    {"source_id": "medlineplus-gone", "english_url": "https://medlineplus.gov/gone.html", "topic": "fever"},
]


def test_build_chunks_from_xml() -> None:
    chunks, problems = build_chunks(ET.fromstring(XML), TOPICS, "MedlinePlus.gov")
    by_id = {c["chunk_id"]: c for c in chunks}
    assert set(by_id) == {"medlineplus-fainting-en-01", "medlineplus-fainting-es-01", "medlineplus-burns-en-01"}

    en = by_id["medlineplus-fainting-en-01"]
    assert en["section"] == "Summary"  # short summary kept whole
    assert en["text"] == (
        "What is fainting?\n\nFainting is a temporary loss of consciousness.\n\n"
        "When to get help?\n\nGet help if:\n\n- It happens again\n- You are injured"
    )  # HTML and the trailing "NIH: ..." attribution stripped
    assert en["source_version"] == "2026-11-13"
    assert en["topic"] == "fainting" and en["language"] == "en"

    es = by_id["medlineplus-fainting-es-01"]
    assert es["source_url"] == "https://medlineplus.gov/spanish/fainting.html"
    assert es["source_title"] == "Desmayos"
    assert es["text"] == "El desmayo es una pérdida temporal del conocimiento."
    assert es["section"] == "Resumen"

    assert any("medlineplus-burns: no Spanish" in p for p in problems)
    assert any("medlineplus-gone: English topic not found" in p for p in problems)


def test_long_summary_splits_on_headings_and_keeps_lists_with_lead_in() -> None:
    para = "<p>" + " ".join(["palabra"] * 120) + "</p>"
    items = "".join(f"<li>condición {i} con su excepción</li>" for i in range(30))
    html = (
        f"<h3>¿Qué es?</h3>{para}{para}"
        f"<h3>¿Cuándo pedir ayuda?</h3>{para}<p>Pida ayuda si:</p><ul>{items}</ul>"
    )
    chunks = chunk_summary(html, "es")
    assert [s for s, _ in chunks] == ["¿Qué es?", "¿Qué es?", "¿Cuándo pedir ayuda?", "¿Cuándo pedir ayuda?"]
    assert chunks[3][1].startswith("Pida ayuda si:\n\n- condición 0")
    assert all(estimate_tokens(text) <= MAX_TOKENS for _, text in chunks)
