# onboard-api

Servicio FastAPI a bordo (Python 3.12, uv). Paquete `onboard_api` en `src/`, app `onboard_api.main:app`. Expone lecturas de la tripulación (SQLite) y el asistente local `POST /assistant/messages` (LangGraph, Ollama, ChromaDB). Todo corre en esta máquina.

El asistente médico es soporte informativo. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado. Contrato y uso desde la consola: [`docs/assistant-frontend-integration.md`](../../docs/assistant-frontend-integration.md).

Todos los comandos se ejecutan desde `services/onboard-api`. En Windows, use `PYTHONUTF8=1` si la salida falla con `UnicodeEncodeError`.

## Ejecutar

```sh
uv sync --locked
uv run fastapi dev            # puerto 8000; GET / -> {"status":"ok"}
```

Para el demo con Docker Compose (API, Ollama, preparación de modelos e índice, y simulador), vea [Run the demo](../../README.md#run-the-demo-docker-compose--tauri) en el README raíz. Esta guía describe la ejecución nativa.

Al arrancar se crea `data/onboard.db` si no existe y se aplican las migraciones pendientes (ver [Base de datos](#base-de-datos)). Ollama y ChromaDB se usan solo cuando una petición los necesita.

## Base de datos

SQLite en `ONBOARD_DB_PATH`. Tablas, columnas, valores permitidos y filas de referencia de `sensor_config`: [`db/data-dictionary.md`](../../db/data-dictionary.md). Migraciones SQL: [`db/migrations/onboard/`](../../db/migrations/onboard/), aplicadas por `init_db` (`src/onboard_api/repositories/database.py`) al arrancar. La versión es `PRAGMA user_version`.

## Configuración

Variables de entorno con prefijo `ONBOARD_` (`src/onboard_api/config.py`). No se lee ningún archivo `.env`. Las rutas relativas se resuelven desde el directorio de trabajo.

| Variable | Por defecto | Uso |
|---|---|---|
| `ONBOARD_DB_PATH` | `data/onboard.db` | Archivo SQLite. |
| `ONBOARD_CORS_ORIGINS` | orígenes de Vite (1420) y Tauri | Lista JSON, p. ej. `'["http://localhost:1420"]'`. |
| `ONBOARD_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Servidor Ollama local. |
| `ONBOARD_OLLAMA_CHAT_MODEL` | `qwen2.5:0.5b` | Modelo que redacta la explicación. |
| `ONBOARD_OLLAMA_EMBED_MODEL` | `bge-m3` | Embeddings de ingesta y consulta. Si cambia, hay que reingestar. Debe coincidir con `corpus/manifest.json`. |
| `ONBOARD_OLLAMA_TIMEOUT_SECONDS` | `20.0` | Tiempo de espera por llamada a Ollama. |
| `ONBOARD_CHROMA_PATH` | `data/chroma` | Índice persistente de ChromaDB. |
| `ONBOARD_GUIDES_COLLECTION` | `medical_guides` | Colección. Debe coincidir con `corpus/manifest.json`. |
| `ONBOARD_RETRIEVAL_MAX_DISTANCE` | `0.50` | Distancia coseno máxima de un fragmento recuperado. |
| `ONBOARD_DEMO_EVENTS_PATH` | sin definir | Lista JSON de eventos operativos para el demo, p. ej. `demo/events.example.json`. Se carga al arrancar. |

`demo/events.example.json` trae una alerta de radiación simulada y una alerta de CO₂ de cabina, ambas solo para `ast-02` (los ids de `scripts/seed_demo.py` y `firmware/simulator.py`). Mientras un evento está activo, todo mensaje de esa persona va a la ruta de alarma (`urgency: "immediate"`), incluso "hola". `ast-01` no tiene eventos y sirve para las rutas normales. Un evento con `astronaut_ids: []` aplica a toda la tripulación y tiene el mismo efecto en todos.

## Modelos de Ollama

```sh
ollama pull bge-m3
ollama pull qwen2.5:0.5b
```

Sin el modelo de chat, la respuesta usa el texto de la ficha o de la guía y lo indica en `data_notices`.

## Ingesta del corpus

Fuentes en `corpus/` (`manifest.json` y `curated.json`). La ingesta necesita Ollama con `bge-m3` y escribe en `data/chroma`. Reingestar actualiza los fragmentos por `chunk_id` y borra los que ya no se generan.

```sh
PYTHONUTF8=1 uv run python -m onboard_api.assistant.ingest [--xml PATH] [--dry-run]
```

- Sin `--xml`, descarga el XML más reciente de Health Topics de medlineplus.gov a `data/corpus_cache/`. Es el único paso que usa la red.
- `--xml PATH` reutiliza un XML local, p. ej. `data/corpus_cache/mplus_topics_2026-11-13.xml`.
- `--dry-run` solo parsea y trocea, sin Ollama ni ChromaDB.

`scripts/prepare_demo.py` hace la preparación completa en un paso: espera a Ollama, descarga los modelos que falten y ejecuta la ingesta solo si `ingest-stamp.txt` en `ONBOARD_CHROMA_PATH` no coincide con el corpus y el modelo de embeddings. Es el servicio `demo-init` de Docker Compose. Se puede repetir sin riesgo. Verificado dentro de Compose; el comando nativo de abajo no se ha ejecutado.

```sh
PYTHONUTF8=1 uv run python scripts/prepare_demo.py
```

Evaluación de la recuperación (sale con código 1 si la tasa top-3 queda por debajo del mínimo):

```sh
uv run python -m onboard_api.assistant.ingest.evaluate [--min-hit-rate 0.8]
```

Último resultado (2026-11-14): 144 fragmentos, top-3 39/43 = 91 % en 16 familias de fichas, umbral 0.50.

## Tests

```sh
uv sync --locked
PYTHONUTF8=1 uv run pytest -q
```

Los tests usan dobles para Ollama, ChromaDB y el reloj (`tests/assistant/fakes.py`).

## Probar el POST

Con el servicio en marcha. Se usa `--data-binary @-` porque en Git Bash de Windows `-d '...'` con tildes produjo `"There was an error parsing the body"`.

Alarma (`urgency: "immediate"`, no consulta lecturas, guías ni modelo):

```sh
curl -s -X POST http://127.0.0.1:8000/assistant/messages -H "Content-Type: application/json" --data-binary @- <<'EOF'
{"astronaut_id": "ast-01", "message": "Siento presión en el pecho desde hace un rato y sudor frío"}
EOF
```

Aclaración (`needs_clarification: true` y `clarifying_question`):

```sh
curl -s -X POST http://127.0.0.1:8000/assistant/messages -H "Content-Type: application/json" --data-binary @- <<'EOF'
{"astronaut_id": "ast-01", "message": "Me duele la cabeza"}
EOF
```

Educativa (`urgency: "informational"`, `sources` con `kind: "guide"`, necesita el índice y Ollama):

```sh
curl -s -X POST http://127.0.0.1:8000/assistant/messages -H "Content-Type: application/json" --data-binary @- <<'EOF'
{"message": "¿Qué es el síndrome de adaptación espacial?"}
EOF
```
