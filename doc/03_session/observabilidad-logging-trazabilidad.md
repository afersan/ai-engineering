# 📄 Observabilidad, logging y trazabilidad 🔴 — 16 min

**Autor:** Antonio Perez  
**Tiempo estimado:** ⏳ 16 min

---

## Por qué el logging estándar no es suficiente

Si vienes de desarrollo web, tienes un hábito razonable: registrar errores, requests HTTP, y quizá algún evento de negocio importante. Con eso, cuando algo falla en producción, puedes reconstruir qué pasó.

Con aplicaciones que integran LLMs, ese nivel de logging es ciego. Sabéis que el endpoint `/estimate` respondió un 200 en 4.2 segundos. Lo que no sabéis es: qué prompt se envió exactamente, cuántos tokens consumió, cuánto costó esa llamada, qué modelo respondió (¿fue OpenAI o el fallback a Anthropic?), si la respuesta vino de caché o de una llamada real, ni por qué la estimación generada tiene una calidad dudosa.

En aplicaciones clásicas, el comportamiento del código es determinista — dado el mismo input, la misma lógica produce el mismo output. Con LLMs, el modelo es una caja negra probabilística que puede devolver respuestas diferentes para el mismo prompt, y cuya calidad depende de factores que no controlas directamente (el prompt engineering, el contexto inyectado, el estado interno del modelo). Debuggear esto sin trazabilidad es trabajar a ciegas.

La trazabilidad en aplicaciones con LLMs necesita cubrir tres dimensiones que el logging web convencional no contempla:

- **Qué se envió y qué se recibió.** El prompt completo (system + user), la respuesta literal del modelo, y los parámetros de la llamada (modelo, temperatura, max_tokens).
- **Cuánto costó.** Tokens de entrada, tokens de salida, modelo utilizado, coste económico calculado. Sin esto, un bug en el prompt que genera respuestas desproporcionadamente largas puede multiplicar tu factura antes de que lo notes.
- **Qué camino siguió la llamada.** ¿Se resolvió desde caché? ¿Hubo fallback? ¿Cuántos reintentos? ¿Cuánto tardó cada fase? Esta información es lo que te permite optimizar y diagnosticar.

## Structured logging: la base

El primer paso — y el que implementaremos en la sesión en vivo — es structured logging. No es específico de LLMs, pero es el fundamento sobre el que se construye todo lo demás.

El concepto es simple: en lugar de registrar logs como texto plano (`"LLM call completed in 3.2s"`), los registramos como objetos estructurados con campos tipados que son parseables por máquinas:

```json
{
  "timestamp": "2026-04-02T10:30:15.123Z",
  "level": "info",
  "event": "llm_call_completed",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "tokens_in": 1847,
  "tokens_out": 423,
  "cost_usd": 0.00089,
  "latency_ms": 3215,
  "cache_hit": false,
  "fallback_used": false
}
```

Esta entrada de log contiene exactamente la misma información que el texto plano, pero ahora puedes filtrar por modelo, agregar costes por período, detectar picos de latencia, y calcular tu tasa de cache hit — todo de forma programática, sin parsear strings con regex.

### Structlog: la librería que usaremos

Structlog es la librería de structured logging más madura del ecosistema Python. Su filosofía es que los logs son datos, no strings. Lleva en producción desde 2013 y ha influenciado el diseño de librerías de logging en otros ecosistemas.

La configuración básica para nuestro proyecto:

```python
import structlog
import logging
import os

def configure_logging():
    """Dual config: readable console in development, JSON in production."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    shared_processors = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.EventRenamer("msg"),
    ]

    if os.environ.get("ENV") == "production":
        # Production: JSON output for observability tool ingestion
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level)
            ),
        )
    else:
        # Development: colored console output, human-readable
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level)
            ),
        )
```

La idea clave es la cadena de procesadores (`processors`). Cada procesador recibe el diccionario del evento, lo enriquece o modifica, y lo pasa al siguiente. `add_log_level` añade el nivel de severidad, `TimeStamper` añade el timestamp en ISO-8601, y `EventRenamer` renombra el campo por defecto de `event` a `msg`. El último procesador de la cadena siempre es el renderer — `JSONRenderer` para producción, `ConsoleRenderer` para desarrollo.

La configuración dual (consola bonita en desarrollo, JSON en producción) es un patrón que usaréis en prácticamente todo proyecto. En desarrollo quieres leer logs rápidamente en el terminal. En producción quieres que tus logs sean ingeridos por Elasticsearch, Loki, CloudWatch, o cualquier plataforma de observabilidad — y todas esperan JSON.

### Contexto vinculado al logger

Structlog permite vincular datos contextualmente a un logger con `bind()`. Esto significa que no necesitas repetir campos comunes en cada llamada:

```python
logger = structlog.get_logger()

# Create a logger with context bound to this request
request_logger = logger.bind(
    request_id="req-abc-123",
    endpoint="/estimate",
)

# All logs from this request carry request_id and endpoint automatically
request_logger.info("llm_call_started", model="gpt-4o-mini", tokens_in=1847)
request_logger.info("llm_call_completed", latency_ms=3215, cache_hit=False)
request_logger.warning("fallback_triggered", original_provider="openai", fallback_provider="anthropic")
```

Cada una de esas líneas genera un log JSON completo con `request_id` y `endpoint` incluidos, sin tener que pasarlos en cada llamada. En una aplicación FastAPI, el `bind` se haría en un middleware que asigne un `request_id` único a cada request entrante.

## Qué registrar en cada llamada al LLM

Para nuestro wrapper del Proyecto 1, la información mínima que debemos registrar en cada llamada es:

**Al inicio de la llamada:**

- Modelo solicitado
- Proveedor destino
- Tokens de entrada (estimados o reales)
- Si la llamada se resuelve desde caché

**Al completar la llamada:**

- Tokens de salida
- Latencia total (ms)
- Coste estimado (USD)
- `finish_reason` (¿completó normalmente o se truncó?)
- Si hubo fallback y a qué proveedor

**En caso de error:**

- Tipo de error (timeout, rate limit, auth, server error)
- Proveedor que falló
- Si se intentará fallback
- Número de reintento

Un ejemplo de cómo integrar esto en el wrapper:

```python
import time
import structlog

logger = structlog.get_logger()

class LLMWrapper:
    def completion(self, messages, model):
        call_logger = logger.bind(model=model)
        call_logger.info("llm_call_started")
        start = time.time()

        try:
            response = self._call_provider(messages, model)
            latency = (time.time() - start) * 1000

            call_logger.info(
                "llm_call_completed",
                latency_ms=round(latency, 1),
                tokens_in=response.usage.prompt_tokens,
                tokens_out=response.usage.completion_tokens,
                finish_reason=response.choices[0].finish_reason,
                cache_hit=False,
            )
            return response

        except Exception as e:
            latency = (time.time() - start) * 1000
            call_logger.error(
                "llm_call_failed",
                error_type=type(e).__name__,
                error_msg=str(e),
                latency_ms=round(latency, 1),
            )
            raise
```

Este patrón — log al inicio, log al completar, log en error — es el mismo que se usa para trazar requests HTTP, queries a base de datos, o cualquier operación con latencia. La diferencia es qué campos registramos: tokens y costes en lugar de status codes y row counts.

## Más allá del logging: herramientas de observabilidad para LLMs

El structured logging te da la materia prima. Las herramientas de observabilidad la convierten en información accionable: dashboards, alertas, trazas visuales de flujos complejos, y análisis de costes.

En el ecosistema actual hay dos categorías de herramientas relevantes para aplicaciones con LLMs:

### Herramientas de observabilidad full-stack

Estas herramientas trazan toda tu aplicación — requests HTTP, queries a base de datos, llamadas a APIs externas — y además entienden la capa de LLMs. Su ventaja es que ves el contexto completo: si una estimación tarda 8 segundos, puedes ver si el cuello de botella es el LLM, la base de datos, o la red.

**Pydantic Logfire** es la más relevante para nuestro stack. Está construido por el equipo de Pydantic (la librería de validación que usamos con FastAPI) y sobre OpenTelemetry — el estándar abierto de observabilidad. Lo que lo diferencia de herramientas solo para LLMs:

- **Trazas unificadas:** una única timeline que muestra la request HTTP entrante en FastAPI, la comprobación de caché en Redis, la llamada al LLM, y la respuesta al cliente. Todo conectado como una traza distribuida.
- **Paneles específicos para LLMs:** visualización de conversaciones completas (system/user/assistant), inspección de tool calls, y token tracking por request y por modelo.
- **Monitorización de costes:** tracking de gasto por proveedor, por modelo, y por endpoint. Alertas cuando el coste supera un umbral.
- **Integración nativa con nuestro stack:** wrappers de instrumentación para FastAPI, OpenAI, Anthropic, LiteLLM, y Redis con una línea de código cada uno.
- **SQL sobre los datos:** puedes consultar tus trazas con SQL estándar (PostgreSQL-compatible), lo que permite análisis ad-hoc que los dashboards predefinidos no cubren.

El free tier de Logfire (10 millones de spans/mes) es más que suficiente para un proyecto como el nuestro.

### Herramientas de observabilidad específicas para LLMs

Estas herramientas se centran exclusivamente en la capa de IA: prompts, respuestas, cadenas de razonamiento, evaluaciones de calidad. No ven tu base de datos ni tus requests HTTP, pero entienden los LLMs en profundidad.

**LangSmith** (del equipo de LangChain) es la referencia en esta categoría. Si usas LangChain o LangGraph, la integración es automática — configuras una variable de entorno y cada llamada se traza sin tocar código. Su fortaleza principal es la inspección paso a paso del razonamiento de agentes: qué prompt se envió, qué herramientas decidió usar el agente, qué respuesta devolvió cada paso. Para debuggear agentes complejos, es indispensable. La limitación: si no usas LangChain, gran parte de su valor desaparece.

**Langfuse** es la alternativa open source más completa. Licencia MIT, auto-hosteable, e integrable con cualquier framework via OpenTelemetry o su propio SDK. Ofrece tracing, gestión de prompts, evaluaciones, y datasets para testing — todo en una sola plataforma. El free tier cloud es generoso, y para equipos con requisitos de privacidad la opción self-hosted es viable. Es una opción sólida para equipos que no quieren depender de LangChain ni de herramientas propietarias.

**Helicone** merece mención por su simplicidad radical de integración: cambias una URL base en tu cliente de OpenAI y todo el logging se activa automáticamente. Es la ruta más rápida a tener observabilidad en producción si tu prioridad es velocidad de setup.

### Cuál elegir

Para un proyecto que empieza, la recomendación práctica es:

- **Structlog para logging local** — es lo que implementaremos en la sesión en vivo. No añade dependencias externas y te da logs estructurados que puedes consultar en tu terminal o enviar a cualquier sistema de ingestión.
- **Logfire si quieres observabilidad visual** — la integración con FastAPI y los SDKs de LLMs es nativa, y el free tier es generoso. Es la opción natural para nuestro stack (Pydantic + FastAPI + OpenAI/Anthropic).
- **Langfuse si necesitas open source auto-hosteable** — especialmente si tienes requisitos de privacidad de datos o quieres control total sobre dónde se almacenan las trazas.
- **LangSmith si ya usas LangChain** — lo veremos en los módulos de agentes (sesiones 12-14) donde usaremos LangGraph intensivamente.

No necesitas todas a la vez. Empieza con structlog, que es la base. Añade una herramienta visual cuando el volumen de llamadas haga insostenible debuggear leyendo logs en el terminal.

## Lo que haremos en la sesión en vivo

En el directo implementaremos la capa de structured logging con structlog sobre el wrapper de abstracción del Proyecto 1. Cada llamada al LLM — sea directa, desde caché, o via fallback — quedará registrada con modelo, tokens, coste, latencia, y resultado. Configuraremos la salida dual (consola en desarrollo, JSON en producción) y vincularemos contexto por request.

La integración con herramientas de observabilidad externas (Logfire, Langfuse) la dejaremos como setup opcional que cada alumno puede hacer por su cuenta — el artículo de material asíncrono sobre herramientas de observabilidad (Bloque 6) incluye las referencias necesarias. El structured logging que implementemos en el directo es la base que alimenta cualquiera de esas herramientas: los logs JSON que genera structlog son directamente ingeribles por todas ellas.

---

## Recursos de referencia

- *Better Stack — "A Comprehensive Guide to Python Logging with Structlog" (enero 2026)*
- *Pydantic Logfire — "AI & LLM Observability" (documentación oficial)*
- *Firecrawl — "Best LLM Observability Tools in 2026" (diciembre 2025)*
