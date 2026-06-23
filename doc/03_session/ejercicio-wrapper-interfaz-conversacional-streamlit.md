# ✍️ Ejercicio — Wrapper de interfaz conversacional 🔴

**Autor:** Antonio Perez

---

## Interfaz conversacional con Streamlit para el Proyecto 1

### Objetivo

Añadir una interfaz conversacional web al Proyecto 1 usando Streamlit. Al finalizar, el alumno debe poder pegar una transcripción de reunión en una interfaz de chat y ver la estimación generada por el LLM en streaming, sin necesidad de usar curl, Postman ni Swagger.

### Punto de partida

Tu proyecto de la sesión 02: un backend FastAPI con un endpoint CAG que recibe transcripciones y devuelve estimaciones de software.

### Formato

Fichero Python (`streamlit_app.py`) en la raíz de tu proyecto. Se ejecuta con `streamlit run streamlit_app.py`.

### Niveles

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

Esto le da al usuario visibilidad sobre qué información está usando el modelo para generar la estimación.

### Verificación

Tu ejercicio está completo cuando:

- [ ] `streamlit run streamlit_app.py` abre una interfaz de chat en el navegador
- [ ] Puedes pegar una transcripción de reunión y recibes una estimación de software
- [ ] La conversación persiste en pantalla (puedes hacer varias preguntas seguidas)
- [ ] La respuesta se muestra en streaming, no de golpe
- [ ] La API key se lee desde `.env` o `st.secrets`, no está en el código

### Entregable

Fichero `streamlit_app.py` funcional en tu proyecto.

### Documentación de referencia

- Streamlit chat elements: https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
- SDK de tu proveedor (OpenAI o Anthropic): documentación de streaming
- Streamlit secrets management: https://docs.streamlit.io/develop/concepts/connections/secrets-management

### Nota

El wrapper de abstracción de proveedores, el cacheo inteligente de respuestas y la capa de logging/trazabilidad los implementaremos juntos durante la sesión en vivo. No es necesario que los prepares antes.
