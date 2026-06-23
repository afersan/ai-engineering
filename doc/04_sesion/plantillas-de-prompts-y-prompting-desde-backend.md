# 📄 Plantillas de prompts y prompting desde backend

**Sesión 4** · `04_03`

---

En el bloque 1 dejamos el `estimator` con un formulario en el frontend que produce un `EstimationRequest` tipado. Ese request llega al servicio IA. Ahora hay que componer el prompt y llamar al modelo. La tentación, sobre todo el primer día, es escribir algo así:

```python
@app.post("/estimate")
def estimate(request: EstimationRequest) -> EstimationResponse:
    prompt = f"""You are a project estimator. Estimate the following:
{request.description}
Type: {request.project_type.value}
Detail: {request.detail_level.value}
Format: {request.output_format.value}"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[{"role": "user", "content": prompt}],
    )
    return EstimationResponse(text=response.output_text)

```

Funciona. Lo demuestras al equipo, todo el mundo aplaude. Pasan dos semanas.

Producto descubre que añadir tres ejemplos de estimaciones de calidad mejora notablemente la consistencia. Concatenas más string al f-string. Otra semana después, deciden que para `detail_level=summary` el prompt tiene que ser diferente que para `detail_level=detailed`. Metes un `if` en el código. Aparece el formato `phases_table`, que requiere instrucciones específicas sobre columnas. Otro `if`. Llega un cliente con un caso de proyectos móviles que quiere su propio set de ejemplos. Otro `if`. Al cabo de dos meses tienes un endpoint de 200 líneas donde el prompt está esparcido entre f-strings y condicionales, mezclado con la lógica de Python, y ya nadie sabe exactamente qué prompt está activo en cada caso.

Y entonces aparecen las preguntas que no puedes responder: ¿cómo testeamos esto?, ¿cómo hacemos rollback si la última versión empeora la calidad?, ¿cómo le explico a la persona de producto qué prompt está usando un cliente concreto?, ¿cómo comparo dos versiones del prompt en un eval?

El problema no es el modelo, ni la librería, ni el framework. El problema es que estás tratando el prompt como un mensaje cuando lo que realmente es, en cuanto el producto crece, es **un artefacto de software**.

---

## El prompt como artefacto: tres componentes

Cuando dejas de tratar el prompt como un mensaje y empiezas a tratarlo como un artefacto de software, lo primero que cambia es que dejas de pensar en él como una cadena única. Pasa a ser una composición de tres tipos de contenido que viven en lugares distintos del sistema y que tienen ciclos de vida distintos.

![01-anatomia-prompt.jpg](https://media1-production-mightynetworks.imgix.net/asset/a3a5a7b1-bd31-4d8f-92c0-1561c2d2f1b5/01-anatomia-prompt.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

La **estructura fija** es lo que no cambia entre requests: el rol del modelo, las instrucciones generales, el formato de salida, los ejemplos few-shot, las reglas de seguridad. Es el contrato del producto con el modelo. Vive en el repositorio del servicio IA, en archivos versionados como cualquier otro código. Cuando el equipo descubre que añadir un ejemplo mejora la calidad, lo que cambia es este componente, y el cambio queda registrado en un commit.

Las **variables** son los datos que llegan en cada request: la descripción del proyecto, los archivos adjuntos, el contexto recuperado por RAG, el historial conversacional, los datos del usuario. Vienen en el body del HTTP request al servicio IA y son distintos para cada llamada.

Los **parámetros** son las selecciones que el usuario o el sistema hacen para configurar el comportamiento: nivel de detalle, formato de salida, idioma, tono. Viven en el formulario del frontend y se mapean a campos tipados en el `EstimationRequest`. No son contenido, son modos.

El template es la pieza que une los tres. Tiene la estructura fija escrita literalmente, marcadores donde van las variables, y bloques condicionales que se activan según los parámetros. En tiempo de render, el motor de plantillas (Jinja2 en nuestro caso, ERB o Blade en un stack equivalente) sustituye y compone, y produce un texto único listo para enviar al LLM.

La consecuencia práctica es que la lógica de tu endpoint deja de ser "concatenar un f-string" y pasa a ser "cargar el template, pasarle el contexto, llamar al modelo". El prompt en sí ya no vive en el código, vive al lado del código en archivos `.j2` que pueden leerse, editarse y testearse independientemente.

---

## Cómo se organiza esto en el servicio IA

Trasladar el principio anterior a una estructura de proyecto es directo. Esta es la organización que vamos a usar en el `estimator`:

![02-estructura-archivos.jpg](https://media1-production-mightynetworks.imgix.net/asset/ce960857-01f8-47cd-a8b2-a05930fcaef0/02-estructura-archivos.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

Tres ideas importan en este árbol:

Primero, los prompts viven en su propio directorio (`app/prompts/`), separados del código que los consume. Esto permite que una persona de producto o un *prompt engineer* pueda editar un template sin tocar Python. También permite que las pull requests que solo cambian el prompt sean fáciles de revisar: el diff es legible, no requiere entender la lógica de la aplicación.

Segundo, cada caso de uso tiene su propio subdirectorio (`estimation/`, y mañana `summarization/`, `extraction/`, etc.). Dentro de cada caso de uso, los templates están **versionados por número** (`v1/`, `v2/`). Cuando el equipo prueba una versión nueva del prompt, no edita los archivos existentes: crea un `v2/` al lado del `v1/`. Esto es lo que va a permitir que en la sesión 15 podamos hacer evals comparativos entre versiones, hacer rollback rápido si una versión nueva empeora la calidad, y servir versiones distintas a clientes distintos si fuese necesario.

Tercero, cada versión separa el prompt en piezas con responsabilidades claras: `system.j2` para el rol y las instrucciones, `user.j2` para el bloque que contiene la entrada del usuario, y `examples.j2` para los few-shot que se incluirán dentro del system. Esta separación es la que recomienda Anthropic en su [documentación de prompt templates and variables](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables) y la que mejor encaja con la API de los proveedores, que distinguen explícitamente entre rol `system` y rol `user`.

Veamos los tres archivos de `v1/`. Empezamos por `system.j2`:

```jinja2
You are a senior project estimator with 15+ years of experience
in {{ project_type | replace('_', ' ') }} projects.

Your task is to produce a structured estimate based on the project
description provided by the user. Follow the rules below strictly.

<output_format>
{% if output_format == "phases_table" %}
Return a markdown table with one row per project phase. Required
columns: phase, duration_weeks, cost_eur, confidence_pct.
{% elif output_format == "narrative" %}
Return a flowing prose estimate organised in three paragraphs:
overview, breakdown by phase, main risks.
{% endif %}
</output_format>

<detail_level>{{ detail_level }}</detail_level>

{% if detail_level == "detailed" %}
For every phase, list the assumptions you made and a confidence
interval expressed as a percentage range.
{% endif %}

{% include "estimation/v1/examples.j2" %}

```

Y `user.j2`, que es deliberadamente minimal:

```jinja2
<project_description>
{{ description }}
</project_description>

Estimate this project following the rules above.

```

El `examples.j2` contiene los ejemplos few-shot, que se inyectan dentro del system mediante `{% include %}`. Lo dejamos fuera del artículo para no alargar, pero la idea es la misma: archivo separado, editable sin tocar el resto.

Por último, el loader. Es trivial pero importante porque es el único punto donde el código Python toca los templates:

```python
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import EstimationRequest

PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    undefined=StrictUndefined,
)

def render_estimation_prompt(
    request: EstimationRequest,
    version: str = "v1",
) -> tuple[str, str]:
    system = _env.get_template(f"estimation/{version}/system.j2")
    user = _env.get_template(f"estimation/{version}/user.j2")

    context = {
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "description": request.description,
    }

    return system.render(**context), user.render(**context)

```

Tres detalles que conviene fijar. `StrictUndefined` hace que cualquier variable que el template referencie y no esté en el contexto rompa con un error claro en tiempo de render, en lugar de renderizarse como cadena vacía y producir un prompt malformado en silencio. `trim_blocks` y `lstrip_blocks` controlan los saltos de línea que introducen los bloques `{% %}` para que la salida no tenga espacios sobrantes que despistan al modelo. Y la firma `version: str = "v1"` es lo que va a permitir, en sesiones futuras, llamar al loader con `v2` o con la versión que indique un experimento sin tocar el resto del código.

Y testearlo deja de ser una utopía:

```python
def test_estimation_prompt_includes_description_in_user_block():
    request = EstimationRequest(
        description="Mobile app with login, chat and push notifications.",
        project_type=ProjectType.MOBILE_APP,
        detail_level=DetailLevel.DETAILED,
        output_format=OutputFormat.PHASES_TABLE,
    )

    system, user = render_estimation_prompt(request)

    assert "<project_description>" in user
    assert "Mobile app with login" in user
    assert "phases_table" in system
    assert "confidence_pct" in system

```

No es un test del LLM, es un test del template. Verifica que dado un input estructurado, el prompt resultante contiene lo que tiene que contener. Es barato, rápido y se ejecuta en CI sin costes de API. Cuando alguien edite el template y rompa accidentalmente la inclusión de la descripción, el test lo detecta antes de llegar a producción.

---

## Cómo estructurar el contenido del prompt: XML tags o Markdown

Una decisión que vas a tomar al escribir el primer template, y que afecta a todos los siguientes, es cómo delimitar las secciones dentro del prompt: dónde empieza el bloque de instrucciones, dónde acaba el contexto, dónde se mete el ejemplo. Hay dos convenciones dominantes y conviene saber por qué existen.

![03-xml-vs-markdown.jpg](https://media1-production-mightynetworks.imgix.net/asset/8762f7b6-1967-408e-a3c2-d4954e64a427/03-xml-vs-markdown.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

[Anthropic recomienda explícitamente XML tags](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags) (`<context>`, `<instructions>`, `<example>`, `<output_format>`). Claude está entrenado prestando especial atención a esos delimitadores, y la diferencia es perceptible cuando los prompts crecen: con XML tags el modelo es más fiable distinguiendo qué parte es instrucción y qué parte es dato del usuario.

[OpenAI tiende a delimitadores Markdown](https://platform.openai.com/docs/guides/prompt-engineering) (`## Context`, `## Instructions`, `## Output format`). GPT funciona muy bien con esa convención y la respeta como estructura natural.

En la práctica los dos modelos entienden los dos estilos sin problema. La elección no es absoluta, es de **calibración fina**: si tu proveedor principal es Anthropic, escribe XML tags; si es OpenAI, escribe Markdown. La consistencia importa más que la convención exacta. Y cuando aparece la necesidad de probar un proveedor distinto, lo que se cambia es el delimitador, no el contenido del prompt — esa es una de las ventajas de tener el prompt como template separado.

Una cosa más sobre XML tags: aunque visualmente parezcan etiquetas HTML, no lo son. Son simplemente delimitadores de texto que el modelo reconoce. No hay un parser detrás, no hay schema, no se valida nada. Un `<project_description>...</project_description>` es exactamente lo mismo que un `BEGIN_PROJECT_DESCRIPTION ... END_PROJECT_DESCRIPTION`, solo que más legible y consistente con cómo Claude se entrenó.

---

## Lo que esto cambia en la práctica

Si has llegado hasta aquí, las consecuencias del cambio son fáciles de enumerar:

El prompt vive en el repositorio. Cualquier cambio queda registrado en git con autor, fecha y mensaje, y se puede revisar en una pull request por alguien que no sea el autor. Esto convierte la mejora del prompt en una práctica normal de ingeniería, no en un acto de fe.

El prompt se puede testear. Hay tests que verifican que para un input dado el prompt contiene lo que tiene que contener, y que se ejecutan en CI sin coste de API. Cuando tengas evals reales (sesión 15), también podrás testear que para un input dado el modelo responde como esperas, pero eso es la siguiente capa.

El prompt se puede versionar y comparar. Tener `v1/` y `v2/` al lado permite hacer evals comparativos en cuanto los tengas, hacer rollback en cuanto detectes una regresión, y servir versiones distintas a segmentos distintos si en algún momento hace falta.

El prompt se puede leer sin entender Python. Una persona de producto puede abrir `system.j2`, leerlo, sugerir cambios y entender qué está haciendo el sistema. Esa transparencia desbloquea conversaciones que con f-strings no son posibles.

Y, sobre todo, separar la composición del prompt de la llamada al LLM hace que el endpoint del servicio IA quede limpio:

```python
from openai import OpenAI

from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse

client = OpenAI()

@app.post("/estimate")
def estimate(request: EstimationRequest) -> EstimationResponse:
    system, user = render_estimation_prompt(request)

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return EstimationResponse(text=response.output_text)

```

Compara este endpoint con el del principio del artículo. La diferencia no es solo cosmética. La complejidad del prompt no ha desaparecido, se ha movido a archivos donde puede crecer sin contaminar la lógica de aplicación.

---

## Una nota sobre stacks que no son Python

El patrón es independiente del lenguaje. Si en algún momento construyes esto en Rails como en la implementación de referencia que usa Antonio, lo que cambia son las herramientas, no la estructura: los templates viven en `app/prompts/estimation/v1/system.erb`, una clase de servicio (`app/services/prompts/estimation_renderer.rb`) hace lo que hace `loader.py`, y los tests de RSpec verifican lo mismo que los pytest. ERB hace exactamente lo que hace Jinja2, con sintaxis distinta. Lo que importa es que el prompt sea un artefacto separado, versionado y testeable, no la librería que renderiza.

Recuerda, no obstante, que en el programa el servicio IA es siempre Python. La razón no es que Ruby no sirva para esto (sirve perfectamente), sino que el ecosistema Python para IA tiene mejor soporte cuando lleguemos a structured outputs (Bloque 3), guardrails (Bloque 4), embeddings (sesiones 7-8) y agentes (sesiones 12-14).

---

## Qué haremos en la sesión en vivo

Llegarás a la sesión con la estructura mental para responder por qué un prompt es algo que se versiona, se testea y se mantiene como código.

En la sesión:

- Construiremos en directo la estructura de directorios `app/prompts/` para el `estimator`, escribiendo los tres archivos `.j2` y el `loader.py`.

- Discutiremos cuándo conviene partir el prompt en `system + user + examples` y cuándo basta con un único template, con criterios concretos.

- Veremos los pros y contras de XML tags y Markdown delimiters con ejemplos del mismo caso renderizado en ambos estilos.

- Escribiremos el primer test del template y lo conectaremos a CI para entender qué cambia el día a día del equipo.

- Sentaremos la base para el Bloque 3: el siguiente paso es exigir que la respuesta del modelo sea JSON con schema, no texto libre, y eso solo es posible si el prompt está estructurado como hemos visto aquí.

---

## Recursos de este bloque

**Lecturas complementarias antes de la sesión:**

- Anthropic — [Prompt engineering overview](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview)

- Anthropic — [Use prompt templates and variables](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables)

- Anthropic — [Use XML tags to structure your prompts](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)

- OpenAI — [Prompt engineering](https://platform.openai.com/docs/guides/prompt-engineering)

- Jinja2 — [Template Designer Documentation](https://jinja.palletsprojects.com/en/stable/templates/)

- Anthropic — [Chain complex prompts for stronger performance](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/chain-prompts)

- Anthropic — [Prompt engineering interactive tutorial](https://github.com/anthropics/courses/tree/master/prompt_engineering_interactive_tutorial)

- Anthropic — [Generate a prompt](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/prompt-generator)
