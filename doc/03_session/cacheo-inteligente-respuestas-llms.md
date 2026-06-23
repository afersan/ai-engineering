# 📄 Cacheo inteligente de respuestas de LLMs 🔴 — 19 min

**Autor:** Antonio Perez  
**Tiempo estimado:** ⏳ 19 min

---

## Por qué cachear respuestas de un LLM

En el Proyecto 1, nuestro estimador de software recibe transcripciones de reuniones y genera estimaciones usando CAG. Imaginad este escenario: un project manager pega la misma transcripción dos veces — quizá porque quiere revisar la estimación que obtuvo ayer, o porque cerró la pestaña y volvió a empezar. Sin cacheo, el sistema hace dos llamadas al LLM, paga dos veces los tokens, y el usuario espera dos veces los 3-5 segundos de latencia. La respuesta será prácticamente idéntica (mismo input, mismo contexto, mismo modelo), pero hemos quemado dinero y tiempo para regenerarla.

Esto no es un caso excepcional. En aplicaciones reales con LLMs, los patrones de uso muestran repetición constante. Chatbots de soporte reciben las mismas preguntas una y otra vez. Herramientas de generación de contenido procesan los mismos temas con variaciones mínimas. Asistentes de código resuelven los mismos problemas formulados de forma diferente. Según datos de producción de 2026, el cacheo semántico puede alcanzar tasas de acierto del 40-70% en aplicaciones con tráfico real, lo que se traduce directamente en ahorro de costes y reducción de latencia.

El cacheo de respuestas LLM tiene tres beneficios directos:

- **Latencia:** una respuesta cacheada se devuelve en microsegundos (exact match) o milisegundos (semántico), frente a los segundos que tarda una llamada al LLM.
- **Coste:** cada cache hit es una llamada al LLM que no pagas. Con tasas de acierto del 40-60%, el ahorro mensual es significativo.
- **Fiabilidad:** una respuesta cacheada no depende de la disponibilidad del proveedor. Si OpenAI se cae pero la respuesta está en caché, tu sistema sigue funcionando para esas queries.

## Cacheo en LLMs vs cacheo web tradicional

Si venís de desarrollo web, ya conocéis el cacheo: Redis, Memcached, CDN, cache de base de datos. El concepto es el mismo, pero hay una diferencia fundamental que cambia las estrategias.

En cacheo web tradicional, la clave es determinista. Si cacheas la respuesta de `GET /api/users/42`, cualquier petición idéntica a esa URL devuelve la misma respuesta. La clave *es* la URL.

En aplicaciones con LLMs, el input del usuario rara vez es idéntico. "¿Cómo reseteo mi contraseña?", "¿Cuál es el proceso para recuperar la contraseña?" y "He olvidado mi password, ¿qué hago?" son la misma pregunta con tres formulaciones distintas. Un cacheo por exact match solo serviría si el texto es byte por byte idéntico. Para capturar las variaciones necesitas cacheo semántico — y eso requiere embeddings y búsqueda por similitud.

Esto nos da tres capas de cacheo, de más simple a más sofisticado:

1. **Exact match:** comparación exacta del input. Rápido (microsegundos), simple de implementar, pero solo funciona para inputs idénticos.
2. **Cacheo semántico:** convierte el input en un embedding y busca en caché queries con significado similar. Más lento que exact match (milisegundos), pero captura reformulaciones.
3. **Prompt caching del proveedor:** mecanismo nativo de algunos proveedores (Anthropic, OpenAI) que cachea porciones del prompt entre llamadas. No cachea la respuesta completa, sino que reduce el coste de procesar la parte repetida del prompt.

## Exact match: el punto de partida

El exact match es la estrategia que implementaremos en la sesión en vivo y es la correcta para nuestro caso de uso: transcripciones idénticas deben producir la misma estimación, sin necesidad de regenerarla.

La implementación se basa en generar una clave de caché determinista a partir de los parámetros que afectan a la respuesta. No basta con hashear el prompt — si cambias el modelo o la temperatura, la respuesta cambia. Todos los parámetros que influyen en el output deben formar parte de la clave:

```python
import hashlib
import json
import redis
from openai import OpenAI

class LLMCache:
    def __init__(self, redis_url="redis://localhost:6379", ttl=86400):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.client = OpenAI()
        self.ttl = ttl  # 24 horas por defecto

    def _cache_key(self, prompt: str, model: str, system_prompt: str) -> str:
        raw = json.dumps({
            "prompt": prompt,
            "model": model,
            "system_prompt": system_prompt,
        }, sort_keys=True)
        return f"llm:{hashlib.sha256(raw.encode()).hexdigest()}"

    def completion(self, prompt: str, model: str, system_prompt: str) -> dict:
        key = self._cache_key(prompt, model, system_prompt)

        # Try cache first
        cached = self.redis.get(key)
        if cached:
            result = json.loads(cached)
            result["cache_hit"] = True
            return result

        # Cache miss — call to LLM
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        result = {
            "content": response.choices[0].message.content,
            "model": model,
            "tokens_in": response.usage.prompt_tokens,
            "tokens_out": response.usage.completion_tokens,
            "cache_hit": False,
        }

        # Save as caché
        self.redis.setex(key, self.ttl, json.dumps(result))
        return result
```

Observad que el `system_prompt` forma parte de la clave. En nuestro proyecto, el system prompt incluye las estimaciones de ejemplo que alimentan el CAG. Si cambiamos esos ejemplos (porque tenemos estimaciones nuevas), las claves de caché cambian automáticamente y las entradas antiguas expiran por TTL. Esto es invalidación implícita — no necesitamos borrar la caché manualmente.

El TTL (Time To Live) es la decisión más importante. Para nuestro estimador de software, 24 horas es razonable: las transcripciones no cambian, y las estimaciones previas que forman el contexto CAG tampoco cambian con frecuencia. Para una aplicación con datos en tiempo real (precios de bolsa, estado de pedidos), el TTL debería ser de minutos.

## Cacheo semántico: capturar reformulaciones

El exact match tiene una limitación evidente: si un usuario envía la misma transcripción con un espacio extra al final, o con una frase introductoria diferente, el hash cambia y la caché falla. El cacheo semántico resuelve esto comparando el *significado* de los inputs en lugar del texto literal.

El mecanismo es el siguiente: cuando llega una query nueva, la convertimos en un vector (embedding), buscamos en la caché si hay algún vector almacenado con similitud coseno por encima de un umbral, y si lo hay devolvemos la respuesta asociada. Si no, llamamos al LLM, guardamos el vector y la respuesta, y la próxima query similar será un cache hit.

```python
import numpy as np
from openai import OpenAI

class SemanticCache:
    def __init__(self, similarity_threshold=0.95):
        self.client = OpenAI()
        self.entries = []  # (embedding, response)
        self.threshold = similarity_threshold

    def _embed(self, text: str) -> list[float]:
        resp = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return resp.data[0].embedding

    def _cosine_sim(self, a: list[float], b: list[float]) -> float:
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def lookup(self, query: str):
        query_vec = self._embed(query)
        best_score, best_response = 0.0, None

        for vec, response in self.entries:
            score = self._cosine_sim(query_vec, vec)
            if score > best_score:
                best_score, best_response = score, response

        if best_score >= self.threshold:
            return best_response, True  # cache hit

        return None, False  # cache miss

    def store(self, query: str, response: str):
        vec = self._embed(query)
        self.entries.append((vec, response))
```

**El umbral de similitud es el parámetro crítico.** Demasiado alto (0.99) y rara vez tendrás cache hits — solo textos casi idénticos pasarán. Demasiado bajo (0.85) y devolverás respuestas incorrectas — queries parecidas pero con intenciones diferentes serán tratadas como iguales. El punto de partida recomendado es 0.95, y debéis ajustarlo con datos reales de vuestra aplicación.

Un detalle importante: la implementación de arriba almacena los embeddings en memoria y hace búsqueda lineal. Esto funciona para prototipos y volúmenes bajos, pero no escala. Para producción, los embeddings se almacenan en una base de datos vectorial (pgvector, Qdrant, Pinecone) que permite búsqueda aproximada por vecinos más cercanos en milisegundos incluso con millones de entradas. Esto lo veremos en profundidad en las sesiones 07 y 08 del módulo de Data-driven AI, cuando trabajemos con embeddings y bases de datos vectoriales.

## Cacheo multi-nivel: combinando estrategias

En producción, la mejor arquitectura combina ambas capas: exact match como primera línea (la más rápida y barata) y semántico como segunda línea (más lento pero captura más hits).

El flujo es:

1. **Llega una query.** ¿Está en la caché exact match? → Si sí, devolver respuesta (microsegundos).
2. **Exact match miss.** ¿Hay una query semánticamente similar en la caché semántica? → Si sí, devolver respuesta (milisegundos) y promoverla a exact match para futuras consultas idénticas.
3. **Ambas cachés miss.** Llamar al LLM, almacenar la respuesta en ambas cachés.

```python
class MultiLevelCache:
    def __init__(self):
        self.exact = LLMCache()         # L1: exact match with Redis
        self.semantic = SemanticCache()  # L2: semantic embeddings

    def completion(self, prompt, model, system_prompt):
        # L1: exact match
        result = self.exact.completion(prompt, model, system_prompt)
        if result["cache_hit"]:
            return result

        # L2: semantic
        cached_response, is_hit = self.semantic.lookup(prompt)
        if is_hit:
            return {"content": cached_response, "cache_hit": True, "cache_level": "semantic"}

        # Miss: L1 result contains the answer from the LLM
        # Save in semantic cache for future queries
        self.semantic.store(prompt, result["content"])
        return result
```

Este patrón de caché multi-nivel es el mismo que se usa en hardware (L1/L2/L3 en CPUs) y en infraestructura web (CDN → Redis → base de datos). La lógica es universal: las capas rápidas y baratas atrapan los casos fáciles, y las capas más sofisticadas capturan el resto.

## Cuándo cachear y cuándo no

No todo se debe cachear. Hay situaciones donde el cacheo es contraproducente o directamente incorrecto:

**Cachea cuando:**

- Los inputs se repiten con frecuencia (FAQs, transcripciones ya procesadas, consultas recurrentes).
- La respuesta no necesita ser única cada vez (estimaciones, resúmenes, respuestas a preguntas factuales).
- El coste por token es significativo o la latencia afecta la experiencia de usuario.
- Los datos subyacentes cambian con poca frecuencia.

**No cachees cuando:**

- Cada respuesta debe ser única (generación creativa, brainstorming, contenido variado).
- Los datos subyacentes cambian constantemente (precios en tiempo real, inventario, estado de pedidos).
- El contexto del usuario es crítico y varía entre llamadas (personalización, historial de conversación largo).
- La temperatura es alta (>0.7) y esperas variabilidad en las respuestas.

Para nuestro Proyecto 1, el cacheo exact match es claramente apropiado: una misma transcripción con el mismo contexto CAG produce la misma estimación. No hay creatividad involucrada — es una tarea determinista donde la repetibilidad es deseable.

## Invalidación: el problema difícil

Hay una cita famosa en computación: "Solo hay dos problemas difíciles en ciencias de la computación: invalidación de caché, nombrar cosas, y errores off-by-one." La invalidación es el problema de decidir cuándo una entrada de caché ya no es válida y debe descartarse.

Para aplicaciones con LLMs, hay tres estrategias principales:

**TTL (Time To Live):** la más simple. Cada entrada expira después de un tiempo fijo. Funciona bien cuando puedes estimar la vida útil de una respuesta. 24 horas para FAQs, 1 hora para información de producto, 5 minutos para datos semi-dinámicos. Es lo que usamos por defecto.

**Invalidación por evento:** cuando los datos fuente cambian, borras las entradas de caché asociadas. En nuestro proyecto, si actualizamos las estimaciones de ejemplo del contexto CAG, deberíamos invalidar toda la caché — porque las respuestas se generaron con un contexto diferente. Esto se implementa con "tags" o namespaces en la caché.

**Versionado del prompt:** incluir una versión del system prompt en la clave de caché. Cuando cambias el prompt, las claves son automáticamente diferentes y las entradas antiguas expiran por TTL. Es lo que hace nuestra implementación de `_cache_key` al incluir el `system_prompt` como parte del hash.

En la práctica, la combinación de TTL + versionado del prompt es suficiente para la mayoría de aplicaciones. La invalidación por evento es necesaria cuando los datos cambian en momentos impredecibles y la frescura es crítica.

## Métricas: qué medir

Implementar cacheo sin medir su eficacia es como optimizar código sin profiling — estás adivinando. Las métricas fundamentales son:

- **Hit rate:** porcentaje de requests que se resolvieron desde caché. Por debajo del 20%, el cacheo apenas justifica la infraestructura. Por encima del 50%, el ahorro es significativo.
- **Latencia de hit vs miss:** cuánto tarda un cache hit vs una llamada al LLM. La diferencia debería ser de 100-1000x.
- **Coste evitado:** tokens que no se consumieron gracias al cacheo, traducidos a dinero.
- **Tasa de stale responses:** con qué frecuencia se devuelven respuestas que ya no son correctas. Si es alta, tu TTL es demasiado largo o tu invalidación es insuficiente.

Estas métricas las implementaremos como parte de la capa de logging y trazabilidad en la sesión en vivo.

## Lo que haremos en la sesión en vivo

En el directo implementaremos cacheo exact match con Redis sobre el wrapper de abstracción que construiremos para el Proyecto 1. El flujo será: la interfaz Streamlit (que habréis construido en el ejercicio pre-sesión) envía la transcripción → el wrapper comprueba la caché → si hay hit, devuelve la respuesta sin llamar al LLM; si no, llama al proveedor configurado (con fallback), almacena la respuesta, y la devuelve.

El cacheo semántico lo dejaremos como concepto en esta sesión — la implementación real requiere embeddings y búsqueda vectorial, que son el tema central de las sesiones 07 y 08. Para el Proyecto 1 con CAG, el exact match es la estrategia correcta: las transcripciones son documentos largos donde la probabilidad de match exacto es alta, y la búsqueda semántica sobre textos tan largos tiene particularidades que merecen su propio tratamiento.

---

*Recurso de referencia para este artículo:*

- *Reintech — "LLM Caching Strategies: Reduce Response Times by 80-95%" (enero 2026)*
- *AI Echoes — "Benchmarking LLM Exact and Semantic Caching with Redis" (marzo 2026)*
- *Redis Blog — "What is Semantic Caching?" (enero 2026)*
