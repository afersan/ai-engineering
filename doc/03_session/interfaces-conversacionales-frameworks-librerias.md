# 📄 Interfaces conversacionales, frameworks y librerías 🔴 — 13 min

**Autor:** Antonio Perez  
**Tiempo estimado:** ⏳ 13 min

---

## El problema que resuelven estos frameworks

Tienes un endpoint que recibe texto y devuelve una respuesta de un LLM. Funciona. Pero la única forma de probarlo es con curl, Postman o Swagger. Si quieres que alguien no técnico lo use — o simplemente tener una experiencia de chat decente durante el desarrollo — necesitas una interfaz web.

Construirla desde cero con HTML, CSS y JavaScript es perfectamente viable, pero tiene un coste: manejar el estado de la conversación, implementar streaming visual, gestionar la entrada de texto, mostrar indicadores de carga… todo eso es fontanería que ya está resuelta.

Ahí es donde entran los frameworks de interfaz para aplicaciones de IA. Permiten crear una UI funcional en Python puro, sin escribir una línea de JavaScript, y en muchos casos con menos de 50 líneas de código.

## Los tres frameworks principales

En el ecosistema Python actual hay tres opciones dominantes para construir interfaces sobre LLMs: **Streamlit**, **Gradio** y **Chainlit**. Cada uno nació con un propósito diferente, y eso marca sus fortalezas y limitaciones.

### Streamlit

Streamlit es el más generalista de los tres. No fue diseñado específicamente para chatbots — nació como herramienta para crear dashboards y aplicaciones de datos. Con el tiempo incorporó elementos de chat (`st.chat_message`, `st.chat_input`) que lo hacen perfectamente capaz para interfaces conversacionales, pero su ADN sigue siendo el de una herramienta de propósito general.

Su modelo de ejecución es el concepto más importante que debéis entender: **cada vez que el usuario interactúa con la aplicación, Streamlit re-ejecuta todo el script de arriba a abajo**. Esto simplifica enormemente el desarrollo (el código se lee como un script secuencial), pero significa que necesitas `st.session_state` para persistir cualquier dato entre interacciones — incluido el historial de la conversación.

Un chat funcional con streaming en Streamlit se reduce a este patrón:

```python
import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Inicializar historial en session_state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Renderizar historial existente
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Aceptar input del usuario
if prompt := st.chat_input("Escribe tu mensaje"):
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generar y mostrar respuesta con streaming
    with st.chat_message("assistant"):
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=st.session_state.messages,
            stream=True,
        )
        response = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": response})
```

Son 25 líneas. Tienes chat con historial, streaming token a token, y gestión de estado. `st.write_stream` se encarga de recibir el stream del SDK de OpenAI y renderizarlo progresivamente — no necesitas manipular chunks manualmente.

**Puntos fuertes:** la mayor comunidad de los tres, el ecosistema de componentes más rico (gráficos, tablas, mapas, file uploads, sidebars), soporte nativo para multipage, y deployment gratuito en Streamlit Community Cloud. Si tu aplicación necesita algo más que chat (mostrar métricas, formularios, visualizaciones), Streamlit es la opción más natural.

**Limitaciones reales:** el modelo de re-ejecución completa hace difícil implementar interacciones con estado complejo. No puedes tener procesos en background, conexiones websocket persistentes, ni actualizaciones en tiempo real sin workarounds. El diseño visual es funcional pero limitado — personalizar CSS es posible pero estás luchando contra el framework. Y para aplicaciones de chat en producción con autenticación, persistencia de conversaciones y gestión de hilos, se queda corto.

### Gradio

Gradio nació en el ecosistema de Hugging Face con un propósito muy específico: envolver cualquier función Python en una interfaz web para demos de modelos de ML. Su filosofía es input → función → output. Defines qué entra, qué sale, y Gradio genera la UI.

Para interfaces conversacionales, Gradio ofrece `gr.ChatInterface`, que simplifica la creación de chatbots:

```python
import gradio as gr
from openai import OpenAI

client = OpenAI()

def respond(message, history):
    messages = [{"role": "system", "content": "Eres un asistente útil."}]
    for human, assistant in history:
        messages.append({"role": "user", "content": human})
        messages.append({"role": "assistant", "content": assistant})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    return response.choices[0].message.content

demo = gr.ChatInterface(respond, title="Chat con LLM")
demo.launch()
```

**Puntos fuertes:** la ruta más rápida de "tengo una función Python" a "tengo una demo web compartible". El comando `demo.launch(share=True)` genera una URL pública temporal (72 horas) sin necesidad de deployment — ideal para compartir prototipos con stakeholders. La integración con Hugging Face Spaces permite publicar demos permanentes con un push a un repositorio. Para modelos multimodales (imagen, audio, vídeo), tiene componentes nativos que los demás no ofrecen.

**Limitaciones reales:** la gestión de estado es más limitada que en Streamlit (`gr.State()` funciona pero es menos intuitivo que `st.session_state`). Los layouts multipágina no son nativos. Para aplicaciones de chat en producción con autenticación, persistencia de historial y gestión de hilos, Gradio se queda sin capacidades.

### Chainlit

Chainlit es el más joven y el más especializado. No fue diseñado como herramienta general de dashboards ni como plataforma de demos de ML — fue diseñado exclusivamente como la capa de UI para aplicaciones conversacionales con LLMs: chatbots, agentes, asistentes.

Esa especialización se nota. Chainlit ofrece de serie funcionalidades que en Streamlit y Gradio hay que implementar a mano o con librerías externas: streaming nativo, threading de mensajes, visualización paso a paso del razonamiento del agente, recolección de feedback del usuario, autenticación, y persistencia de historial de conversaciones.

```python
import chainlit as cl
from openai import OpenAI

client = OpenAI()

@cl.on_message
async def main(message: cl.Message):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un asistente útil."},
            {"role": "user", "content": message.content}
        ],
    )
    await cl.Message(
        content=response.choices[0].message.content
    ).send()
```

Observad que Chainlit usa `async def` — está construido sobre `asyncio` de Python desde su base, lo que hace que el streaming y las operaciones concurrentes sean naturales y eficientes.

**Puntos fuertes:** la observabilidad integrada es su característica diferencial. Puedes ver la "cadena de pensamiento" del agente: qué prompt se envió, qué herramientas decidió usar, qué respuesta devolvió cada paso. Esto es indispensable para debuggear agentes complejos. Integración nativa con LangChain y LlamaIndex. Autenticación con Azure AD, Google y otros providers. Persistencia de conversaciones out-of-the-box.

**Limitaciones reales:** su foco exclusivo en chat hace que sea incómodo para cualquier UI que no sea conversacional (dashboards, comparativas de datos, formularios complejos). La librería de componentes es mucho más pequeña que la de Streamlit — no tiene gráficos, dataframes ni mapas nativos. La comunidad es más reducida, lo que significa menos ejemplos en Stack Overflow y GitHub Issues. La documentación aún tiene asperezas.

## Cuándo usar cada uno

La elección depende de qué estés construyendo:

**Usa Streamlit** cuando tu aplicación necesita más que chat. Si necesitas sidebars con controles, gráficos, tablas de datos, formularios, o cualquier combinación de elementos interactivos además de la conversación, Streamlit es la opción más natural. También es la mejor elección para prototipado rápido cuando no estás seguro de qué forma final tendrá tu aplicación. Es el framework que usaremos en el ejercicio pre-sesión de esta sesión.

**Usa Gradio** cuando necesitas demos rápidas de modelos, especialmente si trabajas con modelos multimodales (imagen, audio, vídeo) o si tu público objetivo está en el ecosistema de Hugging Face. El share link temporal es imbatible para mostrar un prototipo a un stakeholder en 5 minutos.

**Usa Chainlit** cuando estés construyendo una aplicación de chat seria con agentes. Si necesitas observabilidad del razonamiento del agente, autenticación, persistencia de conversaciones, y threading de mensajes, Chainlit te ahorra semanas de desarrollo. Lo revisaremos con más profundidad en los módulos 4 y 5 cuando trabajemos con agentes.

## ¿Y construirlo desde cero?

Hay una cuarta opción: no usar ningún framework y construir la interfaz directamente con HTML/CSS/JavaScript conectado a tu backend FastAPI. Este enfoque tiene sentido cuando necesitas control total sobre la experiencia de usuario, cuando la interfaz de chat es solo un componente dentro de una aplicación web más grande, o cuando los requisitos de diseño son incompatibles con los frameworks disponibles.

La ventaja es obvia: control absoluto. La desventaja también: tienes que implementar tú mismo el estado de la conversación, el rendering de mensajes, el streaming visual (típicamente con Server-Sent Events o WebSockets), los indicadores de carga, y toda la fontanería que los frameworks te dan gratis.

Para un producto en producción con requisitos específicos de UX, esta suele ser la mejor opción a largo plazo. Para prototipado y validación rápida, los frameworks ahorran tiempo. La clave está en saber cuándo cada enfoque tiene sentido.

## Resumen comparativo

![Resumen comparativo Streamlit vs Gradio vs Chainlit](https://media1-production-mightynetworks.imgix.net/asset/eecf7da6-fc1d-4178-838b-29757271ae6b/d53fca2c9d611a91.png?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

*Recursos de referencia para este artículo:*

- *ATNO for GenAI — "Streamlit vs Gradio vs Chainlit: Building Quick UIs for Your AI Applications" (Medium, marzo 2026)*
- *Streamlit Docs — "Build a basic LLM chat app" (documentación oficial)*
