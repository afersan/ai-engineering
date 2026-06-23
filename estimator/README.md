# Estimator CAG - Servicio de Estimacion de Software con IA

Servicio de estimacion de proyectos de software impulsado por IA, utilizando una arquitectura **Cache Augmented Generation (CAG)** con prompts versionados en Jinja2.

**Rama de entrega pre-sesion 04:** `pre-session-04`

## Que es CAG y por que lo usamos

CAG (Cache Augmented Generation) es un patron de arquitectura donde el contexto relevante se inyecta directamente en el prompt del LLM como texto estatico. En esta fase del proyecto, las estimaciones de referencia se incluyen como ejemplos few-shot dentro del template `system.j2`, sin necesidad de una base de datos vectorial ni busqueda semantica.

## Requisitos previos

- **Docker** y **Docker Compose** instalados (para API + Redis)
- Una **API key** de OpenAI o Anthropic
- **uv** para ejecucion local y tests

## Inicio rapido con Docker (API + Redis)

```bash
cd estimator
cp .env.example .env
# Editar .env y poner tu API key real
docker compose up --build
```

La API queda en `http://localhost:8000`.

## Ejecucion local (API + Streamlit)

```bash
cd estimator
uv sync
cp .env.example .env
# Configurar API keys en .env

# Terminal 1 — API
uv run uvicorn app.main:app --reload

# Terminal 2 — interfaz de producto (formulario Streamlit)
uv run streamlit run streamlit_app.py
# Abrir http://localhost:8501
```

La URL del backend se lee de `ESTIMATOR_API_BASE_URL` (default `http://localhost:8000`).

## Probar el servicio

```bash
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "description": "The client wants to build a mobile app for managing restaurant reservations with user registration, real-time booking, push notifications, and an admin panel for restaurant owners.",
    "project_type": "mobile_app",
    "detail_level": "medium",
    "output_format": "phases_table"
  }'
```

Respuesta esperada:

```json
{
  "text": "...",
  "prompt_version": "v1"
}
```

## Tests

Los tests de template corren sin APIs externas:

```bash
cd estimator
uv run pytest -q
```

## Estructura del proyecto

```
estimator/
├── app/
│   ├── main.py                 # FastAPI, health check, CORS
│   ├── config.py               # Pydantic Settings
│   ├── routers/
│   │   └── estimations.py      # POST /api/v1/estimate
│   ├── services/
│   │   ├── llm_service.py      # Orquestacion y llamada al LLM
│   │   ├── llm_wrapper.py      # LiteLLM, fallback, cache Redis
│   │   └── cache.py            # Cache exact-match
│   ├── schemas/
│   │   └── estimation.py       # EstimationRequest / EstimationResponse
│   └── prompts/
│       ├── loader.py           # render_estimation_prompt()
│       └── estimation/v1/      # Templates Jinja2 versionados
├── streamlit_app.py            # Formulario de producto (st.form)
├── tests/
│   ├── prompts/                # Tests de templates (sin LLM)
│   └── test_estimate_endpoint.py
├── docker-compose.yml
└── pyproject.toml
```

## Sesion 4 — De chat a interfaz de producto

Cambios principales respecto a la sesion 03:

- **Formulario tipado** en Streamlit (`st.form`) en lugar de chat conversacional
- **Schemas Pydantic** con `description`, `project_type`, `detail_level`, `output_format`
- **Prompts Jinja2 versionados** en `app/prompts/estimation/v1/`
- **Respuesta simplificada** con `text` y `prompt_version`
- El wrapper LiteLLM y el cache Redis exact-match se mantienen

## Documentacion interactiva

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Session 05: Conversational Memory (Current)

The estimator now supports multi-turn conversations with session state management.

### New Features

- **Session management:** `POST /sessions` creates a session, `/sessions/{id}/estimate` maintains context
- **Conversational memory:** Sliding window (6 turns) preserves recent context
- **Project metadata:** Extracted facts (name, team size, technologies, scope) injected into system prompts
- **File attachments:** Upload PDFs and Word documents to enrich estimations
- **Updated Streamlit client:** Session persistence, file uploads, metadata display

### Running the Service

```bash
cd estimator

# Start API
uv run uvicorn app.main:app --reload

# Start Streamlit client (separate terminal)
uv run streamlit run streamlit_app.py
```

### API Endpoints

- `POST /api/v1/sessions` → Create new session
- `POST /api/v1/sessions/{session_id}/estimate` → Multi-turn estimation with attachments

### Architecture

See `docs/session-05-implementation.md` for detailed architecture decisions.

**Key choices:**
- Local file text extraction (not multimodal API)
- LLM-based metadata extraction (not regex)
- In-memory session storage (volatile, no persistence)
- Sliding window history (6 turns max)

---

> Este proyecto forma parte del **Master en AI Engineering** y servira como base para evolucionar hacia salida estructurada, guardrails y cache semantico en el directo de la sesion 04.
