# 📄 De interfaz conversacional a interfaz de producto

**Sesión 4** · `04_02`

---

En la sesión 03 dejamos el `estimator` como una aplicación de chat. El usuario abre la web, escribe en un textarea lo que quiere estimar, pulsa enter, y nuestro wrapper de proveedor envía el mensaje al LLM y devuelve la respuesta en streaming. Funciona. Lo demostramos en vivo. Es lo que la mayoría de los productos con IA del mercado hacen hoy.

Y aun así, es la peor versión posible del producto.

Imagina dos managers usando esa misma app para estimar el mismo proyecto. El primero es un PM con 15 años de experiencia que ha pasado por consultoría: escribe un brief de 12 líneas con stack tecnológico, restricciones, perfiles del equipo, hitos clave y formato esperado de salida. Recibe una estimación útil, accionable, con un margen de error razonable. El segundo es un Head of Sales que necesita una cifra para una propuesta comercial: escribe "estimar un CRM para una pyme". Recibe una respuesta vaga, con rangos enormes, llena de "depende de…".

Mismo modelo. Mismo prompt de sistema. Misma temperatura. Resultados radicalmente distintos.

El problema no es el modelo. El problema es que **hemos delegado el prompting al usuario** y la calidad del producto se ha vuelto función de algo que no controlamos: cómo de bien promptea cada persona que abre la app. Eso no es un producto, es una herramienta de poder para usuarios avanzados.

Esta sesión va de cómo dar la vuelta a esa decisión.

---

## El chat es un default, no una decisión de diseño

Cuando un equipo decide "vamos a meter IA en nuestro producto", la mayoría de las veces lo que aparece en la pantalla de diseño es un widget de chat. No porque el chat sea la mejor interfaz para el problema, sino porque es la interfaz que vimos en ChatGPT y nos resultó natural copiar.

Amelia Wattenberger lo formuló muy bien en **[Why Chatbots Are Not the Future](https://wattenberger.com/thoughts/boo-chatbots/):

> *"Compare that to looking at a typical chat interface. The only clue we receive is that we should type characters into the textbox. The interface looks the same as a Google search box, a login form, and a credit card field. Of course, users can learn over time what prompts work well and which don't, but the burden to learn what works still lies with every single user. When it could instead be baked into the interface."*

Esa última frase es la clave: la información sobre qué pedir y cómo pedirlo se puede *hornear* en la interfaz. Cuando dejas un textarea desnudo delante del usuario, le estás pidiendo que adivine qué sabe hacer tu producto y cómo formularlo. Cuando le ofreces un formulario con campos concretos, un selector de modos y un botón con un verbo claro, le estás *enseñando* qué puede hacer y le estás *garantizando* que el resultado va a tener una calidad mínima común.

Karpathy llegó al mismo punto desde otro ángulo en su charla **[Software Is Changing (Again)](https://www.ycombinator.com/library/MW-andrej-karpathy-software-is-changing-again) en la AI Startup School de Y Combinator. Su tesis: los productos con IA que están funcionando hoy no son agentes totalmente autónomos, son aplicaciones de **autonomía parcial** donde el humano y el modelo colaboran a través de una UI cuidadosamente diseñada. Cursor no es un chat, es un editor con un loop de generar → verificar muy bien construido. Perplexity no es ChatGPT con búsqueda, es una interfaz de citación con controles. Linear AI no abre un chat cuando le pides que cree una issue, te muestra un formulario pre-rellenado para que lo confirmes con un click.

El chat puro tiene un sitio: cuando el espacio de problemas es genuinamente abierto y exploratorio. Para todo lo demás, suele ser una mala elección por defecto.

---

## Dónde vive el prompt

La pregunta arquitectónica más útil que puedes hacerte cuando rediseñas una feature con IA es ésta: *¿dónde vive el prompt?*

![01-donde-vive-el-prompt_1.jpg](https://media1-production-mightynetworks.imgix.net/asset/74cd6de2-6561-4ba1-86c8-56df0ade25b9/01-donde-vive-el-prompt_1.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

En la arquitectura de chat (la de la sesión 03), el prompt vive en el textarea del frontend. Es el usuario quien lo escribe. Tu backend es básicamente un proxy: añade un system prompt corto, reenvía el texto del usuario al proveedor y devuelve la respuesta. La inteligencia del producto está distribuida entre tu backend y los miles de usuarios que tendrán que aprender a prompearlo bien.

En la arquitectura de producto, el prompt vive en el backend. El usuario solo proporciona los **parámetros** que el prompt necesita: el tipo de proyecto, el nivel de detalle, el formato de salida, los archivos relevantes. Tu backend toma esos parámetros, los inyecta en una plantilla versionada y compone el prompt completo antes de enviarlo al LLM. El LLM recibe siempre el mismo prompt estructurado, solo cambian las variables.

Las consecuencias prácticas son enormes. Cuando el prompt vive en el backend:

- **Lo puedes versionar.** Cuando descubres que añadir un ejemplo o reformular una instrucción mejora la calidad, lo deployas para todos los usuarios a la vez. No tienes que reentrenar a nadie.

- **Lo puedes testear.** Es código, no un mensaje de chat. Tienes diffs, code review, golden sets que ejecutan los mismos parámetros contra distintas versiones del prompt.

- **Lo puedes optimizar para coste.** Si descubres que `gpt-4o-mini` es suficiente para el 80% de los casos pero `claude-haiku-4-5` es mejor para outputs largos, tu backend enruta. El usuario no se entera.

- **Le quitas la responsabilidad al usuario.** El usuario no tiene que saber qué decirle al modelo. Eso es trabajo tuyo, no suyo.

El cambio de mentalidad es: el prompt es un **artefacto de software**, no un mensaje. Como cualquier artefacto de software, se mantiene en un repositorio, se versiona, se revisa y se testea. Lo veremos en detalle en el Bloque 2.

---

## El espectro de interfaces, no es chat o no-chat

Una vez aceptado el principio anterior, la trampa siguiente es pensar en términos binarios: o pongo un chat o pongo un formulario. La realidad es un espectro.

![02-espectro-interfaces_2.jpg](https://media1-production-mightynetworks.imgix.net/asset/d163b91a-de18-405f-886f-2452a5ad9573/02-espectro-interfaces_2.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

A la izquierda del espectro está el **chat puro**: ChatGPT, [Claude.ai](http://Claude.ai), una caja de texto y nada más. El usuario hace todo el trabajo. Es la opción correcta cuando el problema es genuinamente abierto y exploratorio: "ayúdame a escribir un email", "explícame este concepto", "hagamos brainstorming sobre nombres de producto". No hay forma de poner eso en un formulario sin perder la flexibilidad que da valor.

Un paso a la derecha está el **chat con parámetros**: Perplexity con su selector "Search / Academic / Writing / Math", Notion AI con su menú de modos, ChatGPT con sus GPTs especializados. Sigue siendo conversacional, pero hay parámetros explícitos que el backend usa para componer el prompt. El usuario teclea menos sobre cómo quiere la respuesta y más sobre el contenido.

Más a la derecha aparece el **formulario o acción**: Linear AI cuando creas una issue, Raycast AI con sus comandos contextuales, Cursor cuando aplicas una refactorización. No hay textarea, hay botones y selectores. El prompt está completamente abstraído. El usuario expresa intención ("estimar este proyecto", "resumir este documento", "extraer las acciones de esta reunión") y el producto se encarga del cómo.

En el extremo derecho está la **UI generativa**: el patrón que Vercel popularizó con su [AI SDK 3.0](https://vercel.com/blog/ai-sdk-3-generative-ui), donde el LLM no produce texto sino que escoge qué componente de la UI renderizar y con qué datos. El usuario escribe "muéstrame mis vuelos" y el modelo responde con un componente `<FlightCard>` rellenado, no con párrafos.

La pregunta que debes hacerte para cada feature de IA en tu producto no es "¿chat sí o chat no?" sino **"¿dónde en este espectro encaja mejor lo que estoy construyendo?"**. La respuesta correcta depende de cuánta variabilidad legítima hay en lo que el usuario va a pedir, cuánta consistencia necesitas en la salida, y cuánto espacio hay para enseñar al usuario a través de la interfaz.

Para el `estimator`, la respuesta es clara: la salida tiene que ser consistente, los parámetros relevantes son finitos, y el usuario no tiene por qué aprender a prompear bien para obtener un buen resultado. Pertenece al tercer cuadrante: formulario o acción.

---

## Lo que esto significa para el `estimator`

![03-estimator-antes-despues_1.jpg](https://media1-production-mightynetworks.imgix.net/asset/b17bf8cd-9320-4794-99e9-267fada4461e/03-estimator-antes-despues_1.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

A la izquierda, lo que tenemos ahora: un chat con un textarea libre. A la derecha, hacia donde lo vamos a llevar: un formulario con campos explícitos para la descripción del proyecto, un selector para el tipo de proyecto, un grupo de pills para el nivel de detalle, un selector para el formato de salida y un botón claro para generar la estimación.

Lo importante no es el formulario en sí, sino lo que pasa por debajo. El formulario captura los **parámetros del prompt** (no el prompt). Esos parámetros se mapean a un objeto tipado en el backend. Una plantilla de prompt versionada los inyecta en su sitio. El LLM recibe siempre la misma estructura, solo cambian los valores.

En código (en Python con Pydantic, todo en inglés como manda nuestra convención), el contrato entre frontend y backend deja de ser "una cadena de texto" y pasa a ser algo así:

```
from enum import Enum
from pydantic import BaseModel, Field

class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"

class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"

class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"

class EstimationRequest(BaseModel):
    description: str = Field(min_length=20, max_length=2000)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat

```

El frontend ya no envía un mensaje, envía un `EstimationRequest`. El backend ya no concatena lo que llegue, compone el prompt sustituyendo variables en una plantilla:

```
from jinja2 import Template

ESTIMATION_PROMPT = Template("""
You are a senior project estimator with 15+ years of experience in
{{ project_type_human }} projects.

Estimate the following project. Respect the requested detail level and
output format strictly.

<project_description>
{{ description }}
</project_description>

<output_constraints>
- detail_level: {{ detail_level }}
- output_format: {{ output_format }}
</output_constraints>
""".strip())

def build_prompt(request: EstimationRequest) -> str:
    return ESTIMATION_PROMPT.render(
        description=request.description,
        project_type_human=request.project_type.value.replace("_", " "),
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
    )

```

Tres consecuencias inmediatas:

Primero, dos usuarios que rellenan el formulario igual reciben la misma calidad de respuesta. El prompt es exactamente el mismo. La única variabilidad legítima viene del propio LLM (que también acotaremos en bloques siguientes).

Segundo, cuando descubres que añadir un ejemplo en el prompt mejora la consistencia, lo cambias en `ESTIMATION_PROMPT` y haces deploy. Todos tus usuarios se benefician al instante.

Tercero, has separado el problema en piezas que sí sabes resolver con tu experiencia de fullstack: hay un schema, hay un endpoint, hay validación, hay un test que verifica que `build_prompt` produce el texto esperado para un input dado. La parte mágica del LLM queda contenida en una sola llamada al final, no esparcida por toda la aplicación.

Notarás que aún no estamos forzando que la respuesta del LLM sea estructurada. El usuario rellena un formulario, pero la salida sigue siendo texto libre. Esa es la siguiente capa, la veremos en el Bloque 3 (datos estructurados con JSON Schema). De momento, el cambio que importa es el de la entrada: dejar de delegar el prompting al usuario.

---

## Qué haremos en la sesión en vivo

Llegarás a la sesión con el marco mental para responder a una pregunta que casi nunca se hace en los equipos: *¿el chat es realmente la mejor interfaz para esta feature, o es la primera que se nos ha ocurrido?*. Para el `estimator`, la respuesta ya la tenemos: no.

En la sesión en vivo:

- Rediseñaremos el `estimator` pasando del chat libre a un formulario con parámetros estructurados, manteniendo el wrapper de proveedor de la sesión 03 intacto.

- Discutiremos cómo decidir, ante una feature nueva, en qué punto del espectro situarla, con un par de ejemplos sacados de productos reales que iremos analizando juntos.

- Veremos cómo la interfaz de producto cambia las métricas que importan: ya no es "tasa de respuesta", es "tasa de tareas completadas con calidad consistente", lo que conecta directamente con la evaluación de la sesión 15.

- Sentaremos la base que necesitamos para los siguientes tres bloques: el formulario captura parámetros (Bloque 2: cómo se estructura la plantilla), exigiremos al LLM que devuelva JSON con schema (Bloque 3) y validaremos cada salida antes de mostrarla (Bloque 4).

---

## Recursos de este bloque

**Lecturas complementarias antes de la sesión:**

- Amelia Wattenberger — [Why Chatbots Are Not the Future](https://wattenberger.com/thoughts/boo-chatbots/)

- Vercel — [Introducing AI SDK 3.0 with Generative UI support](https://vercel.com/blog/ai-sdk-3-generative-ui)

- Nielsen Norman Group — [Generative UI and Outcome-Oriented Design](https://www.nngroup.com/articles/generative-ui/)

- Andrej Karpathy — [Software Is Changing (Again)](https://www.ycombinator.com/library/MW-andrej-karpathy-software-is-changing-again) (vídeo, ~40 min)

- Latent Space — [Notas y transcripción de la charla de Karpathy](https://www.latent.space/p/s3)

- The New Stack — [Vercel's json-render: A step toward generative UI](https://thenewstack.io/vercels-json-render-a-step-toward-generative-ui/)

- Fast Company — [Why the next AI wave won't revolve around chatbots](https://www.fastcompany.com/91034315/these-three-companies-show-why-the-next-ai-wave-wont-revolve-around-chatbots)
