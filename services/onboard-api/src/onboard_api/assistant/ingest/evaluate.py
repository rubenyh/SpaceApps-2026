"""Retrieval evaluation against the ingested `medical_guides` collection.

    uv run python -m onboard_api.assistant.ingest.evaluate [--min-hit-rate 0.8]

For each Spanish query (at least one positive and one hard query per card family) it
checks whether an expected source_id appears in the top 3 (no topic filter, so this
tests the embedding itself) and prints the top 3 with cosine distances. Unrelated
"negative" queries show how close off-topic text gets, which is what the
`retrieval_max_distance` threshold must cut.

Exit code 1 when the top-3 hit rate (positive + hard) is below --min-hit-rate
(default 0.8: hard queries are paraphrased on purpose, so a few misses are expected;
below 80% the corpus or the model needs attention).
"""

import argparse
import sys

from onboard_api.assistant.integrations import DependencyUnavailable
from onboard_api.assistant.integrations.chroma import GuideRetriever
from onboard_api.assistant.integrations.ollama import OllamaClient
from onboard_api.config import Settings

MP = "medlineplus-"

# (card family, kind, query, expected source_ids)
CASES: list[tuple[str, str, str, list[str]]] = [
    ("breathing_difficulty", "positive", "Me falta el aire y respiro con dificultad", [MP + "breathingproblems"]),
    ("breathing_difficulty", "positive", "¿Qué factores alteran la lectura del oxímetro de pulso?", ["fda-pulse-oximeters"]),
    ("breathing_difficulty", "hard", "Siento que no me entra suficiente aire aunque el oxímetro marca bien", [MP + "breathingproblems", "fda-pulse-oximeters"]),
    ("chest_pain", "positive", "Tengo dolor y presión en el pecho", [MP + "chestpain", "cdc-heart-attack"]),
    ("chest_pain", "hard", "Siento un peso que me aprieta detrás del esternón y baja al brazo izquierdo", ["cdc-heart-attack", MP + "chestpain"]),
    ("palpitations", "positive", "¿Qué es una arritmia del corazón?", [MP + "arrhythmia"]),
    ("palpitations", "hard", "Noto que el corazón se salta latidos o aletea", [MP + "arrhythmia"]),
    ("neurologic_red_flags", "positive", "Señales de un accidente cerebrovascular", ["cdc-stroke-signs", MP + "stroke"]),
    ("neurologic_red_flags", "hard", "Se le torció la boca y no puede levantar bien un brazo", ["cdc-stroke-signs", MP + "stroke"]),
    ("neurologic_red_flags", "hard", "Un dolor de cabeza muy fuerte que empezó de golpe", [MP + "headache", "cdc-stroke-signs", MP + "stroke"]),
    ("loss_of_consciousness_or_seizure", "positive", "Qué hacer si un compañero tiene una convulsión", ["cdc-seizure-first-aid", MP + "seizures"]),
    ("loss_of_consciousness_or_seizure", "hard", "Se quedó rígido, temblando y no respondía durante un minuto", ["cdc-seizure-first-aid", MP + "seizures"]),
    ("loss_of_consciousness_or_seizure", "positive", "Me desmayé un momento y luego me recuperé", [MP + "fainting"]),
    ("severe_allergic_reaction", "positive", "Reacción alérgica grave o anafilaxia", [MP + "anaphylaxis"]),
    ("severe_allergic_reaction", "hard", "Después de comer se me hinchó la lengua y me pica la garganta", [MP + "anaphylaxis"]),
    ("fever_or_respiratory_illness", "positive", "Tengo fiebre, ¿qué significa?", [MP + "fever"]),
    ("fever_or_respiratory_illness", "hard", "Tengo escalofríos y me siento muy caliente desde anoche", [MP + "fever"]),
    ("dizziness_or_space_motion_sickness", "positive", "¿Qué es el síndrome de adaptación espacial?", ["nasa-sas"]),
    ("dizziness_or_space_motion_sickness", "positive", "Diferencia entre mareo y vértigo", [MP + "dizzinessandvertigo"]),
    ("dizziness_or_space_motion_sickness", "hard", "Desde que llegamos a microgravedad todo me da vueltas al mover la cabeza y tengo náuseas", ["nasa-sas", MP + "motionsickness", MP + "dizzinessandvertigo"]),
    ("vomiting_diarrhea_or_dehydration", "positive", "Síntomas de deshidratación", [MP + "dehydration"]),
    ("vomiting_diarrhea_or_dehydration", "hard", "Llevo todo el día vomitando, casi no orino y tengo mucha sed", [MP + "dehydration", MP + "nauseaandvomiting"]),
    ("vomiting_diarrhea_or_dehydration", "positive", "¿Cuándo es grave la diarrea?", [MP + "diarrhea"]),
    ("abdominal_pain_or_gi_bleeding", "positive", "Tengo dolor abdominal fuerte", [MP + "abdominalpain"]),
    ("abdominal_pain_or_gi_bleeding", "hard", "Vomité algo oscuro con sangre", [MP + "nauseaandvomiting", MP + "bleeding", MP + "abdominalpain"]),
    ("heat_illness", "positive", "Síntomas del golpe de calor", ["niosh-heat-illnesses"]),
    ("heat_illness", "hard", "Después de entrenar en el módulo caluroso estoy confuso y sudo muchísimo", ["niosh-heat-illnesses"]),
    ("urinary_symptoms", "positive", "Ardor al orinar y ganas de orinar muy seguido", ["niddk-bladder-infection", MP + "urinarytractinfections"]),
    ("urinary_symptoms", "hard", "Tengo fiebre, escalofríos y dolor en el costado de la espalda", ["niddk-kidney-infection"]),
    ("urinary_symptoms", "hard", "Un dolor intenso en el costado que viene en oleadas", ["niddk-kidney-stones", MP + "kidneystones"]),
    ("urinary_symptoms", "hard", "No puedo orinar desde hace horas y me duele el bajo vientre", ["niddk-urinary-retention"]),
    ("muscle_symptoms", "positive", "Calambres musculares", [MP + "musclecramps"]),
    ("muscle_symptoms", "hard", "Después del ejercicio me duelen mucho los músculos y la orina salió color cola", ["niosh-rhabdo"]),
    ("injury_bleeding_or_burn", "positive", "Señales de peligro tras un golpe en la cabeza", ["cdc-heads-up-signs", MP + "headinjuries"]),
    ("injury_bleeding_or_burn", "hard", "Me di contra un panel y ahora vomito y estoy cada vez más confundido", ["cdc-heads-up-signs", MP + "headinjuries"]),
    ("injury_bleeding_or_burn", "positive", "Me quemé la mano con una superficie caliente", [MP + "burns"]),
    ("injury_bleeding_or_burn", "positive", "Una herida que no para de sangrar", [MP + "bleeding"]),
    ("cabin_environment_alert", "positive", "Síntomas de CO2 elevado en la cabina", ["nasa-co2"]),
    ("cabin_environment_alert", "hard", "Varios compañeros tienen dolor de cabeza a la vez en el mismo módulo", ["nasa-co2", "cdc-co-clinical", MP + "carbonmonoxidepoisoning"]),
    ("cabin_environment_alert", "positive", "Intoxicación por monóxido de carbono y el oxímetro de pulso", ["cdc-co-clinical", MP + "carbonmonoxidepoisoning"]),
    ("radiation_alert", "positive", "Síntomas del síndrome agudo por radiación", ["cdc-ars"]),
    ("radiation_alert", "hard", "¿Puede un análisis de mi orina decir si recibí radiación?", ["cdc-urine-radionuclide"]),
    ("radiation_alert", "positive", "¿Qué dosímetros lleva la tripulación en Orion?", ["nasa-artemis2-dosimetry"]),
]

NEGATIVE = [
    "¿Cómo reinicio el panel de comunicaciones?",
    "¿Cuál es la capital de Francia?",
    "Receta para preparar café en microgravedad",
    "¿A qué hora es la próxima ventana de comunicación con Tierra?",
    "Cambiar el filtro de la cámara del módulo",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m onboard_api.assistant.ingest.evaluate")
    parser.add_argument("--min-hit-rate", type=float, default=0.8)
    args = parser.parse_args(argv)

    settings = Settings()
    ollama = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        settings.ollama_timeout_seconds,
    )
    # No threshold here: we want to see raw distances, then judge the threshold.
    retriever = GuideRetriever(settings.chroma_path, settings.guides_collection, ollama, 2.0)

    hits = 0
    expected_distances: list[float] = []  # best expected hit per query that hit
    try:
        for family, kind, query, expected in CASES:
            top = retriever.search(query, k=3, language="es")
            found = [h for h in top if h.source_id in expected]
            hits += bool(found)
            if found:
                expected_distances.append(found[0].distance)
            print(f"[{'HIT ' if found else 'MISS'}] {family} ({kind}): {query}")
            print(f"       expected {expected}")
            for h in top:
                print(f"       {h.distance:.3f} {h.chunk_id} | {h.section}")
        print("\nNegative (off-topic) queries:")
        negative_distances = []
        for query in NEGATIVE:
            top = retriever.search(query, k=1, language="es")
            negative_distances.append(top[0].distance if top else 2.0)
            print(f"       {negative_distances[-1]:.3f} {top[0].chunk_id if top else '-'} | {query}")
    except DependencyUnavailable as exc:
        print(f"Evaluation failed: {exc}")
        return 2

    rate = hits / len(CASES)
    families = {c[0] for c in CASES}
    print(f"\nTop-3 hit rate: {hits}/{len(CASES)} = {rate:.0%} across {len(families)} card families")
    print(f"Configured retrieval_max_distance: {settings.retrieval_max_distance}")
    print("threshold  expected-hits-kept  negatives-passing")
    for t in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55):
        kept = sum(d <= t for d in expected_distances)
        passing = sum(d <= t for d in negative_distances)
        print(f"   {t:.2f}         {kept:3}/{len(expected_distances)}              {passing}/{len(NEGATIVE)}")
    if expected_distances:
        print(f"Worst expected hit distance: {max(expected_distances):.3f}")
    print(f"Closest negative distance: {min(negative_distances):.3f}")
    if rate < args.min_hit_rate:
        print(f"FAIL: hit rate below {args.min_hit_rate:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
