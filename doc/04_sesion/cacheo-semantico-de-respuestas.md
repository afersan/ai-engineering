# 📄 Cacheo semántico de respuestas

**Sesión 4** · `04_06`

**Tiempo estimado:** ⏳ 25 min

---

Llegas a este bloque con un `estimator` que es ya un producto serio. El formulario produce parámetros tipados, los prompts viven en templates Jinja2 versionados, las respuestas vienen como JSON estructurado validado por Pydantic, y los guardrails filtran inputs problemáticos y outputs inseguros. El servicio IA hace lo que tiene que hacer: convertir una intención del usuario en una estimación coherente y segura.

Y también es un servicio caro y lento.

Pongamos un escenario realista. El equipo de ventas usa el `estimator` durante todo el día para hacer estimaciones rápidas en llamadas con clientes potenciales. Un mismo proyecto típico —"app móvil con login, chat y notificaciones push"— acaba siendo estimado quince veces durante una semana, por personas distintas, con palabras ligeramente distintas:

- *"Mobile app with login, chat and push notifications"*

- *"Aplicación móvil con login, chat y notificaciones push"*

- *"App: needs auth, messaging, push notifs"*

- *"Mobile, login + chat + push, standard onboarding"*

- *"App móvil tipo WhatsApp con autenticación"*

Quince inputs, una sola intención. Cada uno cuesta unos céntimos al LLM y entre 3 y 5 segundos de espera. Multiplica por todas las intenciones que se repiten en una organización durante un mes y la factura empieza a doler. Más doloroso aún es la latencia: el equipo de ventas no quiere esperar 4 segundos en mitad de una llamada.

El cache exact-match que ya tienes desde la sesión 03 no ayuda aquí. Está diseñado para devolver lo cacheado cuando el input es **literalmente el mismo string**, y los inputs humanos casi nunca lo son. Necesitas algo distinto: una capa que reconozca que dos textos distintos están pidiendo lo mismo, y devuelva la respuesta cacheada del primero al resto. Eso es el cacheo semántico, y es el último componente que vamos a meter al `estimator`.

---

## La diferencia con el cache exact-match

Antes de mirar la mecánica, conviene ver el contraste de manera concreta.

![01-exact-vs-semantic.jpg](https://media1-production-mightynetworks.imgix.net/asset/b2904330-7c8f-4d09-b241-e1d3feb4db4f/01-exact-vs-semantic.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

El cache exact-match funciona con string equality. Lo que hash ya viste en clase de algoritmos de primer año: una clave entra en una hash map, si existe la devuelves, si no la guardas. El problema no es el algoritmo, es que la clave que estamos usando —el texto del usuario— no es estable. Cualquier diferencia tipográfica, idiomática o de orden de palabras genera una clave nueva. Para un sistema con LLM, donde los inputs son texto natural, el cache exact-match captura básicamente nada salvo cuando el mismo usuario reenvía el mismo request.

El cache semántico cambia la pregunta. En lugar de comparar strings, compara **significados**. Para hacer eso necesita un mecanismo capaz de medir cuánto se parecen dos textos en su contenido, independientemente de las palabras concretas. Ese mecanismo son los *embeddings*: representaciones vectoriales del texto en un espacio de muchas dimensiones (típicamente 1.536 con los modelos de OpenAI, o entre 768 y 4.096 según el modelo). Dos textos que dicen lo mismo, aunque uno esté en inglés y otro en español, producen vectores que están cerca en ese espacio. Dos textos que no tienen nada que ver producen vectores lejanos.

La mecánica del cache semántico es entonces directa:

1. Cuando llega un request, se calcula el embedding del input.

2. Se busca en el cache el vector más cercano al del input.

3. Si la similaridad coseno entre ambos supera un threshold (típicamente entre 0.85 y 0.95), se considera que es un hit y se devuelve la respuesta cacheada del vecino.

4. Si no, es un miss: se llama al LLM, y al volver se guarda la pareja (embedding del input, respuesta) en el cache.

El [artículo de Redis sobre semantic caching](https://redis.io/blog/what-is-semantic-caching/), que es la lectura obligatoria de este bloque, explica con detalle el mecanismo y los trade-offs. Tres números que conviene tener en mente desde el principio: el embedding tarda entre 50 y 100 ms en computarse, la búsqueda vectorial añade entre 5 y 20 ms, y la latencia de un hit es típicamente 2-4 veces menor que la de un miss completo, llegando a 50-100 veces menor en los casos más favorables. La cuenta sale a favor del cache en cualquier servicio con volumen razonable de queries semánticamente repetitivas.

---

## El threshold como decisión de producto

Aquí es donde el cache semántico se parece más a los guardrails del bloque anterior que al cache que conocías. La búsqueda vectorial no devuelve un binario "hit / miss", devuelve un **score de similaridad** entre 0 y 1, y tú decides a partir de qué umbral consideras que dos inputs son "el mismo".

La elección del threshold es una decisión de producto con implicaciones reales:

Un threshold **agresivo** (0.85, por ejemplo) maximiza los hits y minimiza el coste, pero introduce el riesgo de servir una respuesta cacheada para una pregunta que no era *exactamente* la misma. Si el `estimator` tiene en cache una estimación para "mobile app with login, chat and push" y llega un request por "mobile app with login, chat and *Stripe payments*", un threshold demasiado bajo podría devolver la primera estimación ignorando que el usuario añadió pagos. La estimación cacheada va a estar mal, y como pasó por el cache nunca se llegó a llamar al LLM para corregirla.

Un threshold **conservador** (0.95) elimina prácticamente esos falsos positivos, pero también reduce los hits a los casos donde el input es casi idéntico, perdiendo gran parte del beneficio.

La regla pragmática, igual que con los guardrails, es **desplegar en modo "log-only" primero**. Computa el embedding y haz el lookup, pero **no uses** el resultado: deja que la llamada al LLM ocurra siempre. Logea cada par (input, top-1 vecino encontrado, score) y revísalo durante una o dos semanas. Mira los falsos positivos potenciales: casos donde el score fue alto pero el contenido del input era materialmente diferente. Ajusta el threshold con esos datos. Cuando lo tengas calibrado, activas el bypass del LLM cuando hay hit.

El threshold típicamente se sitúa entre 0.90 y 0.93 para casos como el `estimator`. Los productos que toleran menos error (jurídico, médico, financiero) tienden a 0.95+. Los que priorizan velocidad sobre precisión bajan a 0.85.

---

## Decisiones arquitectónicas en el `estimator`

Tres decisiones importantes hay que tomar al integrar cache semántico al servicio IA. Las tres tienen una respuesta correcta para nuestro caso, pero conviene entender por qué.

### Qué se cachea: la cache key compuesta

La primera decisión es qué se considera "el mismo input". Si solo embedeas la `description` y haces similarity search, dos requests con la misma descripción pero distinto `output_format` o `detail_level` van a colisionar: el primero genera una estimación en formato narrativo y el segundo recibe esa misma estimación cuando había pedido tabla por fases. Mal.

La solución es una **cache key compuesta**: una parte determinista que incluye los parámetros estructurados, y una parte vectorial que es el embedding de la descripción libre.

![02-pipeline-con-cache.jpg](https://media1-production-mightynetworks.imgix.net/asset/397dab19-7000-402d-8e95-377c807a1259/02-pipeline-con-cache.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

La parte determinista funciona como un *bucket*: agrupa requests que tienen los mismos parámetros estructurales. Dentro de cada bucket, la búsqueda por similaridad solo compara descripciones que ya comparten contexto (mismo tipo de proyecto, mismo nivel de detalle, mismo formato de salida, **misma versión del prompt**). El threshold puede entonces ser más agresivo porque el espacio de comparación es más homogéneo.

La inclusión de `prompt_version` en la parte determinista es deliberada. Cuando promociones el prompt a `v2`, todos los buckets de `v1` quedan automáticamente fuera de uso: nadie pregunta por ellos, las nuevas requests crean buckets nuevos en `v2`, y el TTL de Redis acaba limpiando los antiguos. **No tienes que invalidar nada manualmente.** Esa es una de las ventajas no obvias de tener prompts versionados como artefactos en el repositorio que ya planteamos en el bloque sobre plantillas.

### Cuándo se cachea: solo después de los guardrails

La segunda decisión es **cuándo** se escribe al cache. La respuesta correcta es: solo después de que la respuesta haya pasado todos los guardrails, sintácticos y semánticos.

Si cacheas antes de validar, estás guardando potencialmente respuestas con problemas (alucinaciones, formato incorrecto, contenido fuera de scope) y sirviéndolas a futuras requests sin posibilidad de detectar el fallo. Esto es lo que avisé al final del bloque anterior: **el cache propaga errores tan rápido como propaga aciertos**. Si el LLM tuvo un mal momento y devolvió una estimación absurda, esa estimación absurda va a servirse a todos los usuarios cuyo input se parezca al del usuario inicial, durante todo el TTL.

La regla queda así: solo entran al cache respuestas que pasaron el `model_validator`, los validators custom de Guardrails AI, y cualquier check semántico que tengas configurado. El cache es la última escritura del pipeline, no la primera.

### Cuándo se sirven los hits: antes o después de los input guardrails

Hay una tercera decisión que merece pensarse: cuando llega un request, ¿pasa los input guardrails primero y luego mira el cache, o mira el cache primero y solo pasa los guardrails si hay miss?

La respuesta correcta es **input guardrails primero, cache después**. Aunque parezca contraintuitivo (un hit en cache es supuestamente más rápido y barato), saltarse los input guardrails para ahorrar 50 ms tiene consecuencias graves: significaría que un atacante que sabe que cierto contenido tóxico está en el cache puede hacer un prompt injection que active el hit y reciba la respuesta cacheada sin pasar moderación. El input guardrail no es solo para protegerse del LLM, es para protegerse del cache también.

El pipeline completo queda entonces así:

![03-cache-key-compuesta.jpg](https://media1-production-mightynetworks.imgix.net/asset/05bb412a-cdd9-4209-8a84-379e8e55fa84/03-cache-key-compuesta.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

---

## Implementación con Redis

El stack que vamos a usar en el `estimator` es Redis con la librería `redisvl`, que abstrae el manejo de índices vectoriales en Redis y ofrece una clase `SemanticCache` lista para usar. El motivo de la elección es doble: por un lado, Redis es el stack de referencia del bloque y vamos a usarlo también en sesiones 7 y 8 cuando profundicemos en bases de datos vectoriales; por otro, `SemanticCache` resuelve los detalles de bajo nivel (cómo se almacena el vector, cómo se hace el TTL, cómo se hace la búsqueda) y permite concentrarse en el patrón.

Una versión muy simplificada del flujo, integrada en el endpoint del servicio IA:

```python
from redisvl.extensions.llmcache import SemanticCache
from openai import OpenAI

cache = SemanticCache(
    name="estimation_cache",
    redis_url="redis://localhost:6379",
    distance_threshold=0.08,  # equivalente a sim ≥ 0.92
    ttl=86400,
)

embeddings_client = OpenAI()

def cache_lookup(request: EstimationRequest) -> EstimationResult | None:
    bucket = build_bucket_key(request)
    embedding = embed_description(request.description)

    hit = cache.check(
        prompt=embedding,
        filter_expression=f"@bucket:{{{bucket}}}",
        num_results=1,
    )
    if hit:
        return EstimationResult.model_validate_json(hit[0]["response"])
    return None

def cache_write(request: EstimationRequest, result: EstimationResult) -> None:
    bucket = build_bucket_key(request)
    embedding = embed_description(request.description)

    cache.store(
        prompt=embedding,
        response=result.model_dump_json(),
        metadata={"bucket": bucket},
    )

def build_bucket_key(request: EstimationRequest, version: str = "v1") -> str:
    return ":".join([
        version,
        request.project_type.value,
        request.detail_level.value,
        request.output_format.value,
    ])

```

Y la integración en el endpoint:

```python
@app.post("/estimate")
def estimate(request: EstimationRequest) -> EstimationResponse:
    validate_input(request.description)  # input guardrails

    cached = cache_lookup(request)
    if cached is not None:
        return EstimationResponse(result=cached, prompt_version="v1", cached=True)

    system, user = render_estimation_prompt(request)
    result = llm_client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=EstimationResult,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    # output guardrails ya van dentro de los validators de Pydantic
    cache_write(request, result)

    return EstimationResponse(result=result, prompt_version="v1", cached=False)

```

Dos detalles importantes en este código:

El campo `cached: bool` en `EstimationResponse` es valioso para el frontend y para observabilidad. Permite mostrar al usuario que la respuesta vino del cache (puede afectar a la confianza percibida) y permite medir la tasa real de hits en producción para ajustar el threshold con datos.

El embedding se computa **dos veces** en un miss completo: una para el lookup y otra para el write. Esto es deliberadamente subóptimo en aras de la legibilidad. En producción se computa una sola vez y se reutiliza, pero el código del artículo prioriza claridad sobre microoptimización.

Hay alternativas a `redisvl` que merece la pena conocer para tomar la decisión con criterio. [LangCache](https://redis.io/langcache/) es la versión gestionada de Redis para semantic caching de LLMs, sin necesidad de levantar infraestructura. `langchain.cache.RedisSemanticCache` ofrece una abstracción similar dentro del ecosistema LangChain. Y siempre puedes implementar lo mismo manualmente con cualquier vector store (Pinecone, Qdrant, pgvector) si tu stack ya incluye uno. La elección depende menos de la calidad técnica y más de qué dependencias quieres añadir al servicio.

---

## El coste real

Como con los guardrails, conviene mirar la cuenta antes de implementar. El cacheo semántico introduce dos costes nuevos: latencia de embedding (50-100 ms por request, hit o miss) y coste de embedding (céntimos por mil tokens).

A cambio ahorra latencia de LLM (1-5 segundos por hit) y coste de LLM (céntimos por hit en modelos baratos, mucho más en modelos grandes).

La cuenta es favorable cuando la **tasa de hits es lo suficientemente alta como para justificar el overhead constante** de calcular el embedding en todas las requests. Para servicios con un patrón de queries muy repetitivo (chatbots de soporte, FAQs internos, herramientas de estimación como la nuestra), la tasa puede ser del 40-60% y el cache se paga solo en latencia y dinero. Para servicios donde cada query es única (asistentes de escritura creativa, brainstorming, tareas que dependen del contexto del usuario), la tasa puede ser del 5% o menos y el cache puede acabar añadiendo más latencia neta de la que ahorra.

La pregunta práctica es: ¿qué porcentaje de tus queries son re-formulaciones de queries anteriores? Si no lo sabes, el experimento previo es trivial: monta el cache en modo log-only durante una semana, mide la tasa de hits potenciales, y decide.

Una observación sobre el TTL. El default de Redis es 24 horas, que funciona bien para casos como el `estimator` donde los proyectos a estimar no cambian en cuestión de horas. Para casos con datos volátiles (precios, inventario, información en tiempo real), TTLs más cortos (5-15 minutos) son obligatorios. Y cuando subas a `v2` del prompt, recuerda: no necesitas borrar nada, los buckets antiguos quedan huérfanos automáticamente.

---

## Una nota sobre stacks que no son Python

En Ruby, Redis es un stack natural y la gema `redis-rb` cubre las operaciones básicas; para vector search se requiere Redis 7.2+ con el módulo RediSearch, accedido vía comandos directos o con `redis-search-rb`. La parte que falta respecto a Python es una librería equivalente a `redisvl`: hay que escribir más boilerplate, pero el patrón funciona igual. En PHP/Laravel, `predis` o el cliente oficial `phpredis` permiten lo mismo, con las mismas consideraciones.

En todos los casos, lo que vive en el servicio IA es la lógica completa del cache: el backend de negocio simplemente recibe el `EstimationResponse` con el campo `cached: true | false` si quiere usarlo para algo (mostrar el indicador, métricas, etc.). La complejidad del cache no contamina el resto de la aplicación.

---

## Qué haremos en la sesión en vivo

Llegarás a la sesión con el marco mental para razonar sobre cuándo el cacheo semántico aporta valor, cómo se compone una cache key correcta, y por qué los guardrails y el cache deben ordenarse de una forma muy concreta.

En la sesión:

- Levantaremos juntos un Redis local con `redisvl` y conectaremos `SemanticCache` al `estimator` con el código que hemos visto aquí, integrando todas las capas anteriores (guardrails, structured outputs, prompts versionados).

- Veremos en directo cómo se comporta el cache con inputs reales: cuáles producen hits, cuáles producen misses, y cómo evolucionan los scores de similaridad.

- Tocaremos el modo log-only y el ajuste de threshold con datos sintéticos preparados para la sesión.

- Discutiremos las alternativas (LangCache, LangChain RedisSemanticCache, implementación manual sobre pgvector) y los criterios para elegir entre ellas en un proyecto real.

- Cerraremos la sesión revisitando todo el pipeline del `estimator`: la diferencia entre lo que entregaste como ejercicio previo y lo que ahora es un servicio IA listo para producción, con sus cinco capas de validación y su cache.

A partir de aquí, en las próximas sesiones, los embeddings y los índices vectoriales que hoy hemos usado como una abstracción dejan de ser caja negra: en la sesión 7 entendemos qué hay dentro de un embedding, en la sesión 8 entendemos cómo funciona la búsqueda vectorial por debajo, y volveremos al cache del `estimator` para reescribirlo de forma informada cuando el RAG entre en juego.

---

## Recursos de este bloque

**Lecturas complementarias antes de la sesión:**

- Redis — [What is semantic caching? Guide to faster, smarter LLM apps](https://redis.io/blog/what-is-semantic-caching/)

- Redis — `redisvl`[Semantic Cache documentation](https://docs.redisvl.com/en/latest/user_guide/llmcache_03.html)

- Redis — [LangCache (managed semantic caching service)](https://redis.io/langcache/)

- Zilliz — [Semantic Cache: Accelerating AI with Lightning-Fast Data Retrieval](https://zilliz.com/learn/semantic-cache-accelerate-AI-with-lightning-fast-data-retrieval)

- LangChain — [Caching guide for LLMs](https://python.langchain.com/docs/integrations/llm_caching/)
