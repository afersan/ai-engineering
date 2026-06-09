# Estimator CAG - Servicio de Estimacion de Software con IA

Servicio de estimacion de proyectos de software impulsado por IA, utilizando una arquitectura **Cache Augmented Generation (CAG)** con capa de abstraccion LLM, cache Redis, streaming SSE e interfaz Streamlit.

## Que es CAG y por que lo usamos

CAG (Cache Augmented Generation) es un patron de arquitectura donde el contexto relevante se inyecta directamente en el prompt del LLM como texto estatico. En esta fase del proyecto, las estimaciones de referencia se incluyen como ejemplos dentro del prompt del sistema, sin necesidad de una base de datos vectorial ni busqueda semantica.

## Novedades sesion 03 (v0.2.0)

- **Wrapper LLM** con LiteLLM y fallback automatico OpenAI → Anthropic
- **Cache exact-match** en Redis para transcripciones identicas
- **Streaming SSE** en `POST /api/v1/estimate/stream`
- **Observabilidad** ampliada: `request_id`, tokens, latencia, coste, cache hit
- **Interfaz Streamlit** conversacional con chat y streaming

## Requisitos previos

- **Docker** y **Docker Compose** instalados (recomendado)
- API keys de **OpenAI** y/o **Anthropic**
- **Redis** (incluido en Docker Compose)

## Inicio rapido con Docker (recomendado)

1. Entrar al directorio:
   ```bash
   cd estimator
   ```

2. Configurar variables de entorno:
   ```bash
   cp .env.example .env
   # Editar .env con tus API keys
   ```

3. Levantar API + Redis:
   ```bash
   docker compose up --build
   ```

4. API disponible en `http://localhost:8000`

## Interfaz Streamlit

En una terminal aparte (con la API corriendo):

```bash
cd estimator
uv sync
uv run streamlit run streamlit_app.py
```

Abre `http://localhost:8501` para usar el chat conversacional.

## Alternativa: ejecucion local sin Docker

```bash
cd estimator
uv sync
cp .env.example .env
# Levantar Redis localmente o desactivar cache: CACHE_ENABLED=false
uv run uvicorn app.main:app --reload
```

## Probar el servicio

### Estimacion sincrona

```bash
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "transcription": "The client wants to build a mobile app for managing restaurant reservations. They need user registration, a restaurant search with filters by cuisine and location, a real-time reservation system with availability checking, push notifications for reservation confirmations and reminders, and an admin panel for restaurant owners to manage their listings and view analytics."
  }'
```

### Estimacion en streaming (SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/estimate/stream \
  -H "Content-Type: application/json" \
  -d '{"transcription": "The client wants to build a mobile app..."}'
```

## Estructura del proyecto

```
estimator/
├── app/
│   ├── main.py                 # FastAPI, middleware request_id, CORS
│   ├── config.py               # Settings (Redis, cache, LLM)
│   ├── routers/
│   │   └── estimations.py      # POST /estimate y /estimate/stream
│   ├── services/
│   │   ├── llm_service.py      # Logica CAG + delegacion al wrapper
│   │   ├── llm_wrapper.py      # LiteLLM Router, fallback, logging
│   │   └── llm_cache.py        # Cache exact-match Redis
│   ├── schemas/
│   │   └── estimation.py
│   └── context/
│       └── examples.py         # Ejemplos CAG
├── streamlit_app.py            # Interfaz conversacional
├── tests/
├── Dockerfile
├── docker-compose.yml          # API + Redis
└── pyproject.toml
```

## Variables de entorno

| Variable | Default | Descripcion |
|----------|---------|-------------|
| OPENAI_API_KEY | — | Requerida si LLM_PROVIDER=openai |
| ANTHROPIC_API_KEY | — | Requerida para fallback |
| LLM_MODEL | gpt-4o-mini | Modelo primario |
| LLM_FALLBACK_MODEL | claude-haiku-4-5 | Modelo de respaldo |
| REDIS_URL | redis://localhost:6379/0 | Conexion Redis |
| CACHE_ENABLED | true | Activar/desactivar cache |
| CACHE_TTL_SECONDS | 86400 | TTL cache (24h) |
| API_BASE_URL | http://localhost:8000 | URL API para Streamlit |

## Tests

```bash
cd estimator
uv run pytest
```

## Documentacion interactiva

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

> Este proyecto forma parte del **Master en AI Engineering** y evolucionara hacia RAG con base de datos vectorial en modulos posteriores.
