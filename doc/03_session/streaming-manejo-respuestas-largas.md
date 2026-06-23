# 📄 Streaming y manejo de respuestas largas 🔴 — 18 min

**Autor:** Antonio Perez  
**Tiempo estimado:** ⏳ 18 min

---

## El problema de la respuesta monolítica

Cuando nuestro estimador de software del Proyecto 1 recibe una transcripción larga y genera una estimación detallada, el usuario vive una experiencia predecible: pulsa enviar, ve un spinner durante 5-10 segundos, y de golpe aparece un bloque de texto completo. Durante esos segundos no hay ningún feedback visual de que algo esté ocurriendo. El usuario no sabe si el sistema está procesando, si se ha colgado, o si ha perdido conexión.

Este es el comportamiento por defecto de una API REST convencional: el servidor genera la respuesta completa, y solo cuando está terminada la envía al cliente de una sola vez. Funciona bien cuando la respuesta tarda milisegundos. Funciona mal cuando un LLM tarda segundos en generar cientos de tokens.

El streaming resuelve esto enviando la respuesta al cliente fragmento a fragmento, a medida que el LLM la genera. El usuario ve el texto "escribiéndose" en tiempo real — exactamente como ocurre en ChatGPT, Claude o cualquier interfaz de chat moderna. La percepción de velocidad cambia radicalmente: aunque el tiempo total de generación sea el mismo, el usuario recibe el primer token en milisegundos en lugar de esperar al último.

Además del beneficio de UX, el streaming permite que el cliente empiece a procesar la respuesta antes de que termine. En nuestro caso, un project manager puede empezar a leer el resumen de la estimación mientras el LLM aún está generando el desglose detallado por fases.

## Tres mecanismos, un objetivo

Para enviar datos del servidor al cliente de forma progresiva, hay tres mecanismos disponibles en el ecosistema HTTP. Cada uno opera a un nivel diferente y tiene implicaciones distintas para vuestra arquitectura.

### StreamingResponse (chunked transfer)

Es el mecanismo más básico. FastAPI envía la respuesta HTTP con el header `Transfer-Encoding: chunked` en lugar de `Content-Length`. Esto le dice al cliente: "no sé cuánto mide la respuesta total, pero te voy enviando trozos a medida que estén listos."

El servidor genera chunks con un generador Python asíncrono, y FastAPI los transmite automáticamente. El cliente lee del stream con `response.body.getReader()` y procesa cada chunk a medida que llega.

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import OpenAI

app = FastAPI()
client = OpenAI()

async def generate_estimation(transcription: str):
    """Async generator that yields chunks from the LLM response."""
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a software estimation expert..."},
            {"role": "user", "content": transcription},
        ],
        stream=True,
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content

@app.post("/estimate")
async def estimate(transcription: str):
    return StreamingResponse(
        generate_estimation(transcription),
        media_type="text/plain",
    )
```

El punto clave es `stream=True` en la llamada a OpenAI. En lugar de esperar a que el modelo termine de generar toda la respuesta, la API empieza a devolver tokens parciales inmediatamente. Cada `chunk.choices[0].delta.content` contiene un fragmento de texto (a veces una palabra, a veces una parte de palabra) que nuestro generador `yield`ea al `StreamingResponse`.

En el lado del cliente, el JavaScript es ligeramente más complejo que una llamada REST normal:

```javascript
const response = await fetch('/estimate', { method: 'POST', body: transcription });
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    document.getElementById('result').innerText += text;
}
```

La diferencia con una llamada REST convencional es que en lugar de hacer `await response.json()` (que espera a la respuesta completa), obtenemos un `ReadableStreamReader` y leemos chunks en un bucle. Cada chunk se decodifica y se añade al DOM inmediatamente.

**Cuándo usar StreamingResponse:** cuando estás enviando datos crudos (texto plano, archivos grandes, audio/video) y no necesitas estructura en los eventos. Es el mecanismo con menor overhead del protocolo.

### Server-Sent Events (SSE)

SSE opera un nivel por encima de StreamingResponse. En lugar de enviar bytes crudos, envía eventos estructurados con campos definidos: `data`, `event`, `id`, y `retry`. El Content-Type es `text/event-stream`, y el navegador tiene una API nativa (`EventSource`) para consumirlo.

La diferencia práctica más importante es que SSE añade estructura y resiliencia. Cada evento puede tener un tipo y un identificador, lo que permite al cliente reaccionar de forma diferente según el tipo de dato que recibe. Y si la conexión se corta, el navegador reconecta automáticamente y envía el último `id` recibido, lo que permite al servidor retomar desde donde se quedó.

Desde la versión 0.135.0, FastAPI tiene soporte nativo para SSE con `EventSourceResponse`:

```python
from collections.abc import AsyncIterable
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent

app = FastAPI()

@app.post("/estimate/stream", response_class=EventSourceResponse)
async def estimate_stream(transcription: str) -> AsyncIterable[ServerSentEvent]:
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcription},
        ],
        stream=True,
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield ServerSentEvent(data=content)
```

En versiones anteriores de FastAPI, necesitabas la librería `sse-starlette` para esto. Con FastAPI moderno, `EventSourceResponse` y `ServerSentEvent` son ciudadanos de primera clase.

En el cliente, el código es más limpio que con StreamingResponse porque el navegador maneja el protocolo:

```javascript
const eventSource = new EventSource('/estimate/stream');

eventSource.onmessage = function(event) {
    document.getElementById('result').innerText += event.data;
};

eventSource.onerror = function() {
    eventSource.close();
};
```

`EventSource` gestiona la conexión, el parseo de eventos, y la reconexión automática. No necesitas un `ReadableStreamReader` ni un bucle manual.

**Cuándo usar SSE:** cuando necesitas eventos estructurados (por ejemplo, enviar tokens de texto en un evento `data` y metadatos como token count en un evento `meta`), cuando la reconexión automática es importante, o cuando quieres la API más limpia posible en el cliente. **Es el mecanismo recomendado para streaming de respuestas LLM en aplicaciones web**, y es el estándar de facto que usan OpenAI y Anthropic en sus propias APIs de streaming.

### WebSockets

WebSockets son un protocolo completamente diferente. Mientras que StreamingResponse y SSE son unidireccionales (servidor → cliente), WebSockets establecen un canal bidireccional y persistente donde ambos lados pueden enviar mensajes en cualquier momento.

La conexión empieza con un handshake HTTP (request GET con `Upgrade: websocket`, respuesta `101 Switching Protocols`) y a partir de ahí la comunicación abandona HTTP por completo — los mensajes viajan como frames WebSocket sobre una conexión TCP persistente.

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive message from client
            transcription = await websocket.receive_text()

            # Stream response back to client
            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcription},
                ],
                stream=True,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    await websocket.send_text(content)

            # Signal end of response
            await websocket.send_text("[END]")
    except Exception:
        await websocket.close()
```

**Cuándo usar WebSockets:** cuando necesitas comunicación bidireccional real — el cliente envía mensajes y el servidor responde, todo sobre la misma conexión persistente. Esto es exactamente lo que hace un chat: el usuario escribe, el servidor responde en streaming, el usuario escribe de nuevo. Sin embargo, WebSockets son significativamente más complejos de implementar, testear y escalar. Necesitan gestión de conexiones (qué pasa si el cliente se desconecta), no tienen reconexión automática (la tienes que implementar tú), y no funcionan bien con load balancers sin sticky sessions.

## Cuál usar para nuestro proyecto

Para el Proyecto 1, la elección depende de qué capa de la arquitectura estemos mirando.

**En Streamlit:** no necesitáis implementar ningún mecanismo de streaming a mano. Streamlit abstrae todo esto con `st.write_stream()`, que acepta directamente el stream del SDK de OpenAI o Anthropic y lo renderiza token a token. Es la razón por la que el ejercicio pre-sesión os pide usar `st.write_stream` — Streamlit resuelve el problema de streaming de UI sin que toquéis HTTP.

**En el endpoint FastAPI (para clientes que no sean Streamlit):** SSE es la opción correcta. Ofrece eventos estructurados, reconexión automática, y la implementación es limpia tanto en servidor como en cliente. Es lo que implementaremos en la sesión en vivo cuando conectemos el wrapper de abstracción con capacidad de streaming.

**WebSockets** los reservamos para más adelante en el programa, cuando las aplicaciones de chat necesiten comunicación bidireccional real (por ejemplo, cuando un agente necesite pedir clarificaciones al usuario durante una tarea larga).

## Streaming con diferentes proveedores

Un detalle práctico que debéis tener en cuenta: cada proveedor de LLM implementa el streaming de forma ligeramente diferente en su SDK.

Con **OpenAI**, el stream devuelve objetos `ChatCompletionChunk` donde el contenido está en `chunk.choices[0].delta.content`:

```python
stream = openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    stream=True,
)
for chunk in stream:
    text = chunk.choices[0].delta.content or ""
    yield text
```

Con **Anthropic**, el patrón es diferente — usas un context manager y escuchas eventos de tipo `text`:

```python
with anthropic_client.messages.stream(
    model="claude-haiku-4-5",
    messages=messages,
    max_tokens=4096,
) as stream:
    for text in stream.text_stream:
        yield text
```

Esta diferencia en las APIs de streaming es otro argumento a favor de la capa de abstracción que discutimos en el artículo anterior. Si usáis LiteLLM, la interfaz de streaming es uniforme independientemente del proveedor:

```python
from litellm import completion

response = completion(
    model="gpt-4o-mini",  # or "claude-haiku-4-5", same interface
    messages=messages,
    stream=True,
)
for chunk in response:
    text = chunk.choices[0].delta.content or ""
    yield text
```

El formato de streaming de LiteLLM sigue la convención de OpenAI para todos los proveedores. Cambiáis el modelo en la configuración y el código de streaming no se toca.

## Manejo de respuestas largas

El streaming resuelve el problema de UX (el usuario ve la respuesta mientras se genera), pero hay otro problema asociado: ¿qué pasa cuando la respuesta es *demasiado* larga?

Los modelos tienen un límite de tokens de salida (`max_tokens` o `max_completion_tokens`). Si la estimación de software es tan detallada que excede ese límite, la respuesta se corta abruptamente — el modelo deja de generar sin terminar la frase. Esto es particularmente problemático en nuestro caso, donde una estimación incompleta es potencialmente peor que no tener estimación.

Hay varias estrategias para manejar esto:

**Configurar `max_tokens` explícitamente** y elegir un valor que deje margen suficiente para la respuesta completa. Si vuestras estimaciones típicas son de 500-800 tokens, configurar `max_tokens=2000` da un margen cómodo. El coste por token de salida es fijo, pero solo pagas los tokens que se generan — configurar un máximo alto no cuesta más si la respuesta real es corta.

**Detectar truncamiento** en el campo `finish_reason` de la respuesta. Si el modelo devuelve `finish_reason="length"` (en lugar de `"stop"`), la respuesta fue cortada por el límite de tokens. En ese caso, podéis hacer una segunda llamada pidiendo que continúe, o devolver un aviso al usuario.

**Diseñar el prompt para controlar la longitud.** Incluir en el system prompt instrucciones como "genera una estimación concisa de máximo 500 palabras" ayuda a que el modelo se mantenga dentro de límites razonables. No es una garantía — los modelos no cuentan palabras con precisión — pero reduce significativamente las respuestas desbordadas.

Para nuestro Proyecto 1, la combinación de un `max_tokens` generoso y la detección de `finish_reason` es suficiente. Las estrategias más sofisticadas (dividir la generación en múltiples llamadas, resumir progresivamente) las veremos en el módulo de RAG avanzado cuando las respuestas sinteticen múltiples fuentes.

## Lo que haremos en la sesión en vivo

En el directo, integraremos streaming en el wrapper de abstracción del Proyecto 1. El flujo completo será: el usuario pega una transcripción en Streamlit → Streamlit llama al wrapper → el wrapper comprueba la caché (si hay hit, devuelve la respuesta completa; si no, llama al LLM con `stream=True`) → los tokens se envían progresivamente a Streamlit via `st.write_stream`.

También configuraremos un endpoint SSE en FastAPI para que clientes externos (no Streamlit) puedan consumir las estimaciones en streaming. Esto deja el backend preparado para cualquier frontend futuro que queráis conectar.

---

*Recurso de referencia para este artículo:*

- *Hassaan Bin Aslam — "Streaming Responses in FastAPI" (enero 2025)*
- *FastAPI Docs — "Server-Sent Events (SSE)" (documentación oficial)*
- *Sevalla — "Real-time OpenAI Response Streaming with FastAPI" (noviembre 2025)*
