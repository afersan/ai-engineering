# Sesión 3: Patrones de diseño para wrappers de modelos — 89 min

**Autor:** Antonio Perez  
**Tiempo estimado de lectura:** ⏳ 4 min

---

## Introducción

¡Hola!

En la sesión anterior construiste la primera versión funcional del sistema. Tenías un endpoint que respondía, pero aún estabas lejos de algo utilizable en un entorno real.

En esta sesión damos un paso clave: convertir ese backend en un sistema que empieza a comportarse como un producto.

El foco ya no está en que "responda", sino en **cómo responde**, **cómo escala** y **cómo se integra** en un contexto de uso real.

---

En la sesión 02 dejamos el Proyecto 1 con un endpoint CAG funcional. En esta sesión lo convertimos en algo que parece un producto real.

### Lo que vamos a construir

- **Wrapper de abstracción** — una capa sobre el LLM que permite cambiar de proveedor sin tocar lógica de negocio, con fallback automático si uno falla
- **Cacheo inteligente** — transcripciones idénticas no repiten la llamada al modelo. Primera vez: 4 segundos. Segunda vez: instantáneo
- **Streaming con SSE** — el usuario ve la estimación escribiéndose en tiempo real, no un spinner durante 15 segundos
- **Trazabilidad completa** — cada llamada queda registrada con modelo, tokens, coste y latencia
- **Interfaz web conversacional** — Streamlit como cara visible del estimador

Son los patrones que separan un script de demo de un sistema preparado para producción — y los usaréis en cualquier proyecto con LLMs.

**Vídeo de introducción:** [De prototipo a producto (Vimeo)](https://player.vimeo.com/video/1188338107?h=0744605c4e)

---

Durante esta sesión añadirás capas que no suelen aparecer en tutoriales básicos, pero que son imprescindibles en sistemas reales: abstracción, eficiencia, observabilidad y experiencia de usuario.

El resultado no es solo mejor rendimiento, sino un cambio de naturaleza del sistema: pasa de ser un experimento técnico a una base sólida sobre la que construir producto.

---

## Arquitectura del Proyecto 1 en esta sesión

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
│   - Cacheo, logging     │
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
┌─────────┐   ┌──────────┐
│ OpenAI  │   │Anthropic │
└─────────┘   └──────────┘
```

Tu endpoint FastAPI llama al wrapper. El wrapper decide a qué proveedor llamar. Si ese proveedor falla, rota al siguiente. Tu endpoint no sabe ni le importa cuál respondió — recibe una respuesta normalizada y sigue con su lógica de parseo y validación de la estimación.

> **Nota pedagógica:** El ejercicio pre-sesión os pide conectar Streamlit directamente al LLM (sin wrapper). En la sesión en vivo, refactorizaremos esa conexión directa para que pase por el wrapper.

---

## Contenidos obligatorios 🔴

| Recurso | Documento |
|---------|-----------|
| 🎥 Introducción: De prototipo a producto | Vídeo arriba |
| 🗒 Interfaces conversacionales, frameworks y librerías (13 min) | [interfaces-conversacionales-frameworks-librerias.md](./interfaces-conversacionales-frameworks-librerias.md) |
| 🗒 Abstracción de proveedores y estrategias de fallback (20 min) | [abstraccion-proveedores-estrategias-fallback.md](./abstraccion-proveedores-estrategias-fallback.md) |
| 🗒 Cacheo inteligente de respuestas (19 min) | [cacheo-inteligente-respuestas-llms.md](./cacheo-inteligente-respuestas-llms.md) |
| 🗒 Streaming y manejo de respuestas largas (18 min) | [streaming-manejo-respuestas-largas.md](./streaming-manejo-respuestas-largas.md) |
| 🗒 Observabilidad, logging y trazabilidad (16 min) | [observabilidad-logging-trazabilidad.md](./observabilidad-logging-trazabilidad.md) |

---

## Ejercicios prácticos ✍️

### ✍️ Interfaz conversacional con Streamlit para el Proyecto 1

Documento completo: [ejercicio-wrapper-interfaz-conversacional-streamlit.md](./ejercicio-wrapper-interfaz-conversacional-streamlit.md)

**Objetivo:** Añadir una interfaz conversacional web al Proyecto 1 usando Streamlit. Al finalizar, el alumno debe poder pegar una transcripción de reunión en una interfaz de chat y ver la estimación generada por el LLM en streaming, sin necesidad de usar curl, Postman ni Swagger.

**Punto de partida:** Tu proyecto de la sesión 02: un backend FastAPI con un endpoint CAG que recibe transcripciones y devuelve estimaciones de software.

**Formato:** Fichero Python (`streamlit_app.py`) en la raíz de tu proyecto. Se ejecuta con `streamlit run streamlit_app.py`.

#### Niveles

**Nivel 1 — Chat básico (obligatorio)**

Crea una aplicación Streamlit con interfaz de chat (`st.chat_message`, `st.chat_input`) que permita al usuario escribir o pegar una transcripción de reunión. La aplicación debe enviar ese texto al LLM (reutilizando la lógica de llamada que ya tienes del proyecto) y mostrar la estimación resultante como mensaje del asistente.

Requisitos:

- El historial de la conversación debe mantenerse visible durante la sesión (usa `st.session_state`)
- El system prompt debe ser el mismo que usas en tu endpoint CAG (estimador de software)
- La API key no debe estar hardcodeada

**Nivel 2 — Streaming (obligatorio)**

Modifica la aplicación para que la respuesta del LLM se muestre en streaming (token a token) en lugar de aparecer de golpe cuando termina la generación. Usa `st.write_stream` o el patrón de placeholder + delta que prefieras.

El usuario debe ver la estimación "escribiéndose" en tiempo real.

**Nivel 3 — Contexto CAG en la interfaz (opcional)**

Añade un panel lateral (`st.sidebar`) que muestre:

- El system prompt activo (solo lectura)
- El contexto estático inyectado (estimaciones de ejemplo que alimentan el CAG)
- Métricas básicas de la última llamada: modelo utilizado, tokens de entrada, tokens de salida, tiempo de respuesta

#### Verificación

Tu ejercicio está completo cuando:

- [ ] `streamlit run streamlit_app.py` abre una interfaz de chat en el navegador
- [ ] Puedes pegar una transcripción de reunión y recibes una estimación de software
- [ ] La conversación persiste en pantalla (puedes hacer varias preguntas seguidas)
- [ ] La respuesta se muestra en streaming, no de golpe
- [ ] La API key se lee desde `.env` o `st.secrets`, no está en el código

**Entregable:** Fichero `streamlit_app.py` funcional en tu proyecto.

#### Documentación de referencia

- [Streamlit chat elements — Build conversational apps](https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps)
- SDK de tu proveedor (OpenAI o Anthropic): documentación de streaming
- [Streamlit secrets management](https://docs.streamlit.io/develop/concepts/connections/secrets-management)

> **Nota:** El wrapper de abstracción de proveedores, el cacheo inteligente de respuestas y la capa de logging/trazabilidad los implementaremos juntos durante la sesión en vivo. No es necesario que los prepares antes.

---

## Resumen de patrones de la sesión

| Patrón | Problema que resuelve | Herramienta clave |
|--------|----------------------|-------------------|
| Interfaz conversacional | Probar el LLM sin curl/Postman | Streamlit |
| Abstracción de proveedores | Acoplamiento a un único SDK | LiteLLM |
| Fallback automático | Caídas y rate limits del proveedor | LiteLLM Router |
| Cacheo exact match | Coste y latencia en inputs repetidos | Redis |
| Streaming SSE | UX en respuestas largas | FastAPI `EventSourceResponse` |
| Structured logging | Visibilidad de tokens, coste y latencia | structlog |

---

## ❗ Obtén los recursos completos en las siguientes lecciones 👇

Los artículos detallados de cada tema están en los documentos enlazados en la tabla de contenidos obligatorios.

Para finalizar el módulo, evalúa el contenido en la plataforma LIDR: **🆙 Evalúa el contenido de este Módulo**
