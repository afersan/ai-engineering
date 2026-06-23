# 📄 Abstracción de proveedores y estrategias de fallback 🔴 — 20 min

**Autor:** Antonio Perez  
**Tiempo estimado:** ⏳ 20 min

---

## El problema: acoplamiento a un proveedor

En la sesión 02 montamos un endpoint FastAPI que recibe transcripciones de reuniones y genera estimaciones de software usando CAG. Funciona. Pero si miramos el código con honestidad, hay un problema serio: está acoplado a un único proveedor.

Si usas el SDK de OpenAI, tu código importa `openai`, llama a `client.chat.completions.create()`, y parsea un objeto de respuesta con la estructura específica de OpenAI. Si mañana quieres probar Claude porque Anthropic acaba de lanzar un modelo más barato o más capaz para tu caso de uso, no puedes simplemente cambiar una variable de configuración — tienes que reescribir la llamada, adaptar el parseo de la respuesta, manejar errores diferentes, y ajustar la gestión de tokens.

Esto no es un problema teórico. En el ecosistema actual de LLMs, ocurren con frecuencia situaciones como estas:

- **Un proveedor se cae.** OpenAI ha tenido incidentes de disponibilidad documentados. Anthropic también. Si tu sistema depende al 100% de uno solo, tu producto se para cuando ellos se paran.
- **Los precios cambian.** Los proveedores ajustan tarifas regularmente — a veces a la baja (competencia) y a veces al alza. Si estás acoplado, no puedes reaccionar rápido.
- **Aparecen modelos mejores.** Cada trimestre salen modelos nuevos con mejor relación calidad-precio. Si cambiar de modelo implica refactorizar tu backend, simplemente no lo harás — y pagarás de más o tendrás peor calidad.
- **Las APIs evolucionan.** Parámetros nuevos, formatos de respuesta actualizados, endpoints deprecados. Cada cambio en la API del proveedor te obliga a tocar código de producción.

La industria ya resolvió este problema antes. Hace una década, el mundo del desarrollo web dejó de escribir queries SQL a mano contra cada base de datos y adoptó ORMs (Object-Relational Mappers) como SQLAlchemy, Prisma o ActiveRecord. La idea era la misma: poner una capa de abstracción entre tu lógica de negocio y el proveedor de datos, de modo que puedas cambiar de MySQL a PostgreSQL sin reescribir tu aplicación.

Lo que un ORM hace para bases de datos, una capa de abstracción de LLMs lo hace para modelos de lenguaje.

## Qué es una capa de abstracción de LLMs

Es una interfaz unificada que se coloca entre tu código de aplicación y los proveedores de LLMs. En lugar de llamar directamente al SDK de OpenAI o de Anthropic, llamas a una función genérica (`completion()`, por ejemplo) y la capa de abstracción se encarga de traducir esa llamada al formato que espera el proveedor configurado.

El contrato es simple: tu lógica de negocio habla un solo idioma (la interfaz del wrapper), y el wrapper traduce a tantos proveedores como necesites.

En la práctica, esto significa que tu código del Proyecto 1 pasaría de esto:

```python
# Coupled to OpenAI
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcripcion},
    ],
)
estimation = response.choices[0].message.content
```

A algo como esto:

```python
# Decoupled: the provider is configuration, not code
from litellm import completion

response = completion(
    model="gpt-4o-mini",  # Cambiar a "claude-haiku-4-5" = 0 cambios en lógica
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcripcion},
    ],
)
estimation = response.choices[0].message.content
```

El cambio parece menor — un import diferente y una función en vez de un método — pero la implicación es enorme: cambiar de proveedor es ahora un cambio de configuración (`"gpt-4o-mini"` → `"claude-haiku-4-5"`), no un cambio de código. Tu lógica de negocio (el system prompt, el parseo de la estimación, la validación) no se toca.

## Construirlo tú mismo vs usar una herramienta existente

La primera pregunta que os surgirá como desarrolladores senior es: "¿no puedo simplemente escribir yo mi propio wrapper?" Sí, podéis. Y al principio parece la opción más limpia — una clase con un método `call()` que internamente decide si usa OpenAI o Anthropic según una variable de entorno.

El problema es que esa clase crece. Rápido. Estos son los problemas reales que aparecen cuando mantienes un wrapper ad-hoc en producción:

**Mantenimiento continuo.** Cada vez que un proveedor actualiza su API (parámetros nuevos, formatos de respuesta cambiados, endpoints deprecados), tu wrapper necesita una actualización. Con dos proveedores esto es manejable. Con cinco, es un trabajo a tiempo parcial.

**Re-implementar funcionalidades ya resueltas.** Reintentos con backoff exponencial, conteo de tokens por modelo, gestión de rate limits, normalización de respuestas entre proveedores con formatos diferentes, manejo de errores específicos de cada SDK… Todo esto es código que hay que escribir, testear y mantener. Y todo esto ya está resuelto en las herramientas existentes.

**Casos borde no anticipados.** Un wrapper casero no ha sido expuesto a la variedad de situaciones que sí ha enfrentado uno open source con miles de usuarios. Timeouts parciales, respuestas truncadas, errores intermitentes de red, cambios silenciosos en APIs — estos casos aparecen en producción, no en desarrollo.

**El coste real.** El tiempo que tu equipo invierte manteniendo un wrapper es tiempo que no invierte en mejorar tu producto. A largo plazo, la abstracción casera sale más cara que la herramienta existente.

Dicho esto, un wrapper propio tiene sentido en un caso concreto: cuando tu necesidad es muy específica y ninguna herramienta existente la cubre bien. Si solo necesitas llamar a un proveedor con un par de parámetros custom y no planeas cambiar, la complejidad de añadir una dependencia externa puede no justificarse. Pero en la mayoría de proyectos reales — y desde luego en el nuestro — la abstracción merece la pena.

## Herramientas de abstracción disponibles

El ecosistema de herramientas de abstracción se ha consolidado en varias categorías. No son todas equivalentes — cada una resuelve el problema desde un ángulo distinto.

### LiteLLM — El agregador ligero

LiteLLM es la herramienta que vamos a usar por el momento. Es una librería Python open source que expone una interfaz compatible para más de 100 modelos de más de 10 proveedores. Su filosofía es ser ligera: no impone conceptos pesados (ni chains, ni agents, ni pipelines), simplemente estandariza la llamada a cualquier LLM.

Lo que ofrece más allá de la abstracción pura:

- **Router con fallback y reintentos:** puedes configurar una lista de modelos ordenada por prioridad. Si el primero falla, intenta el segundo. Con reintentos configurables y backoff.
- **Tracking de costes:** contabiliza tokens y coste por llamada, por modelo, por usuario.
- **Rate limiting:** evita que superes los límites de cada proveedor.
- **Proxy mode:** puede ejecutarse como servidor intermedio que gestiona todas las llamadas LLM de tu aplicación, útil para equipos donde varios servicios necesitan acceder a LLMs.

Un ejemplo de configuración con fallback:

```python
from litellm import Router

router = Router(
    model_list=[
        {
            "model_name": "estimator",  # nombre lógico que usa tu código
            "litellm_params": {
                "model": "gpt-4o-mini",
                "api_key": "sk-...",
            },
        },
        {
            "model_name": "estimator",  # mismo nombre = fallback automático
            "litellm_params": {
                "model": "claude-haiku-4-5",
                "api_key": "sk-ant-...",
            },
        },
    ],
    fallbacks=[{"estimador": ["estimator"]}],
    num_retries=2,
)

# Your code only knows "estimator" — doesn´t know
# if the answer comes from OpenAI or Anthropic
response = router.completion(
    model="estimator",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcripcion},
    ],
)
```

Observad que el código de negocio usa `model="estimador"` — un nombre lógico definido por nosotros. La resolución de qué modelo físico se usa, y la rotación entre proveedores si hay fallos, es responsabilidad del Router. Tu endpoint FastAPI no sabe ni necesita saber qué proveedor respondió.

**Nota importante sobre seguridad de dependencias:** en marzo de 2026, las versiones 1.82.7 y 1.82.8 de LiteLLM en PyPI fueron comprometidas con código malicioso. El incidente fue detectado y las versiones bloqueadas rápidamente, pero es un recordatorio real de los riesgos de las dependencias en el ecosistema Python. La buena práctica es fijar versiones en vuestro `pyproject.toml` y verificar hashes. Esto aplica a cualquier dependencia, no solo a LiteLLM.

### OpenRouter — El marketplace

OpenRouter funciona como un marketplace de modelos. En lugar de tener una cuenta con cada proveedor, tienes una sola API key de OpenRouter y accedes a decenas de modelos a través de su API unificada. OpenRouter se encarga del routing, la facturación consolidada y, opcionalmente, del balanceo entre proveedores para el mismo modelo.

La ventaja principal es la simplicidad operativa: una cuenta, una factura, un endpoint. La desventaja es que tus datos pasan por sus servidores (lo que puede ser un problema de compliance) y aplican un margen sobre el precio del proveedor original.

OpenRouter tiene sentido para prototipos rápidos y exploración de modelos. Para producción, especialmente si manejas datos sensibles, la mayoría de equipos prefieren llamar directamente a los proveedores con una capa de abstracción local como LiteLLM.

### LangChain — El framework completo

LangChain ofrece abstracción de proveedores como parte de un framework mucho más amplio que incluye chains, agents, memoria, tools, y un ecosistema completo para construir aplicaciones complejas con LLMs.

Para el propósito específico de abstracción de proveedores, LangChain es sobredimensionado. Es como usar Rails para servir una página estática. Donde LangChain brilla es cuando necesitas orquestación compleja — y llegaremos a eso en los módulos 4 y 5 del programa. Para esta sesión, donde solo necesitamos abstraer la llamada al LLM y añadir fallback, LiteLLM es la herramienta correcta por su menor complejidad.

## Estrategias de fallback

La abstracción de proveedores habilita una capacidad fundamental para producción: el fallback automático. Si un proveedor falla, el sistema rota al siguiente sin intervención manual y sin que el usuario note nada.

Hay varias estrategias de fallback, y la elección depende de vuestros requisitos:

### Fallback secuencial (la más común)

Defines una lista ordenada de proveedores. El sistema intenta el primero; si falla (timeout, error 500, rate limit), pasa al segundo; si ese también falla, al tercero. Es lo que configuramos con el Router de LiteLLM en el ejemplo anterior.

Este enfoque es sencillo y predecible. El orden refleja tu preferencia: primero el modelo más barato o más rápido, después los alternativos. La mayoría de aplicaciones en producción usan esta estrategia.

### Fallback por tipo de error

No todos los errores merecen un fallback. Un error de autenticación (API key inválida) no se va a resolver intentando con el mismo proveedor de nuevo, ni con otro si la key también es mala. Un timeout sí justifica un reintento. Un error 429 (rate limit) justifica esperar y reintentar, o rotar a otro proveedor.

La configuración granular permite definir qué errores disparan un reintento en el mismo proveedor, cuáles disparan una rotación a otro proveedor, y cuáles se devuelven directamente al usuario:

```python
# Granular fallback
def call_with_fallback(messages, providers):
    for provider in providers:
        try:
            return provider.call(messages)
        except AuthenticationError:
            raise  # No tiene sentido reintentar ni rotar
        except RateLimitError:
            continue  # Rotar al siguiente proveedor
        except TimeoutError:
            if provider.retries_left > 0:
                provider.retry_with_backoff()
            else:
                continue  # Agotar reintentos y rotar
        except ServerError:
            continue  # El proveedor tiene problemas, rotar
    raise AllProvidersFailedError()
```

### Routing por complejidad (avanzado)

Una estrategia más sofisticada es enrutar la llamada a diferentes modelos según la complejidad de la tarea. Transcripciones cortas y simples van a un modelo económico (gpt-4o-mini, claude-haiku-4-5). Transcripciones complejas con múltiples requisitos técnicos van a un modelo más potente (gpt-4o, claude-sonnet-4-6).

Esto no es exactamente fallback — es routing inteligente. Pero se implementa sobre la misma infraestructura de abstracción y comparte la filosofía de desacoplar la selección del modelo de la lógica de negocio. No lo implementaremos en el ejercicio de esta sesión, pero es un patrón que revisaremos cuando lleguemos a las sesiones de orquestación de agentes.

## La interfaz del wrapper en nuestro proyecto

Para el Proyecto 1, la capa de abstracción que implementaremos en la sesión en vivo seguirá esta arquitectura:

```
┌─────────────────────────┐
│   Interfaz Streamlit    │
│   (sesión 03 - ejerc.)  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│   Endpoint FastAPI      │
│   (sesión 02)           │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│   LLM Wrapper           │  ← Lo que construiremos en el directo
│   - Abstracción         │
│   - Fallback            │
│   - (Cacheo, logging)   │
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
┌─────────┐  ┌──────────┐
│ OpenAI  │  │Anthropic │
└─────────┘  └──────────┘
```

Tu endpoint FastAPI llama al wrapper. El wrapper decide a qué proveedor llamar. Si ese proveedor falla, rota al siguiente. Tu endpoint no sabe ni le importa cuál respondió — recibe una respuesta normalizada y sigue con su lógica de parseo y validación de la estimación.

El ejercicio pre-sesión os pide conectar Streamlit directamente al LLM (sin wrapper). En la sesión en vivo, refactorizaremos esa conexión directa para que pase por el wrapper. Es un momento pedagógico deliberado: primero experimentáis el acoplamiento directo, luego lo resolvemos juntos.

## Criterios para elegir tu herramienta

Si tuviera que resumir los criterios de selección en una guía rápida para vuestros proyectos profesionales:

**Privacidad de datos.** ¿Tus datos pueden pasar por servidores de terceros? Si no (compliance, GDPR, datos sensibles), descarta OpenRouter y cualquier solución que actúe como proxy externo. LiteLLM y wrappers propios mantienen las llamadas directas entre tu infraestructura y el proveedor.

**Complejidad de tu aplicación.** Si solo necesitas abstracción de llamadas + fallback, LiteLLM es la opción más equilibrada. Si necesitas orquestación de agentes, chains, memoria persistente, y herramientas, LangChain justifica su complejidad adicional. Si necesitas un marketplace con facturación consolidada para explorar modelos, OpenRouter es la vía rápida.

**Overhead operativo.** LiteLLM como librería es un `pip install` y una línea de código. LiteLLM como proxy (servidor) requiere infraestructura adicional. LangChain implica aprender un framework con sus propias abstracciones. Evaluad qué nivel de complejidad podéis absorber.

**Madurez y comunidad.** LiteLLM tiene más de 40.000 estrellas en GitHub y es una dependencia transitiva de muchos frameworks de agentes. LangChain es el framework más extendido del ecosistema. OpenRouter es un servicio gestionado con su propia estabilidad. Todos son opciones maduras a estas alturas.

## Lo que viene en la sesión en vivo

Lo importante que debéis llevar claro antes de la sesión: **la abstracción de proveedores no es un lujo arquitectónico — es un requisito para cualquier sistema con LLMs que aspire a producción.** El coste de implementarla es mínimo. El coste de no tenerla aparece el día que tu proveedor se cae, sube precios, o depreca el modelo que usas.

---

*Recurso de referencia para este artículo:*

- *ProxAI — "The LLM Abstraction Layer: Why Your Codebase Needs One in 2025" (septiembre 2025)*
- *LiteLLM — Documentación oficial: Getting Started, Router ([docs.litellm.ai](http://docs.litellm.ai))*
- ProxAI — [https://www.proxai.co/blog/archive/llm-abstraction-layer](https://www.proxai.co/blog/archive/llm-abstraction-layer)
