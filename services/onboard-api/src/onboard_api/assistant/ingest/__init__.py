"""Reproducible corpus ingest into the `medical_guides` ChromaDB collection.

Run from services/onboard-api:
    uv run python -m onboard_api.assistant.ingest [--xml PATH] [--dry-run]
    uv run python -m onboard_api.assistant.ingest.evaluate
"""

from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[4]
CORPUS_DIR = SERVICE_ROOT / "corpus"
CACHE_DIR = Path("data/corpus_cache")  # relative to the cwd, like Settings paths

# Chunk metadata `topic` vocabulary (protocol cards use these in guide_topics).
TOPICS = frozenset(
    """breathing_problems pulse_oximetry chest_pain heart_attack arrhythmia stroke
    headache fainting seizures anaphylaxis fever dizziness_vertigo motion_sickness
    space_adaptation dehydration nausea_vomiting diarrhea abdominal_pain bleeding
    heat_illness rhabdomyolysis muscle_cramps urinary_tract_infections uti_bladder
    kidney_infection kidney_stones urinary_retention head_injury burns carbon_monoxide
    carbon_dioxide radiation_ars radiation_urine_testing dosimetry""".split()
)
