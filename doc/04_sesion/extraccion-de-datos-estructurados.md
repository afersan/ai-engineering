# 📄 Extracción de datos estructurados

**Sesión 4** · `04_04`

---

El ejercicio previo te deja con un `estimator` que ya no es un chat: tienes un formulario en el cliente que produce un `EstimationRequest` tipado, un servicio IA con templates Jinja2 versionados que componen el prompt, y un endpoint que devuelve el `output_text` del LLM. La parte que has construido es sólida.

Y aun así, el frontend tiene un problema que no se ve hasta que intentas renderizarlo. El usuario eligió "tabla por fases" en el formulario. El LLM devuelve algo así:

```
This project will likely take 3 to 4 months in total. Phase 1 is design,
which I estimate at around 4 weeks and approximately 8.000 EUR. Phase 2
is core development...

```

Funciona. Es leíble. Pero la UI tiene que mostrar una tabla con columnas `phase`, `weeks`, `cost_eur`, `confidence_pct`, y lo que tienes es prosa. Si quieres la tabla, alguien tiene que extraer los números: o un parser con regex (frágil, casca cuando el modelo cambia el formato), o un segundo LLM que extraiga (caro, lento, redundante), o pides al usuario que mire el texto y lo entienda él (incoherente con el formulario que acabas de construir).

Esto es lo que la mayoría de equipos descubre la primera vez que mete IA en un producto serio. El LLM es bueno generando contenido, pero el contenido que un producto consume no es texto, son **datos**. Y el camino entre "el modelo me dice algo" y "el frontend renderiza un componente con esos datos" tiene que ser robusto, predecible y testeable.

La buena noticia es que los proveedores ya han resuelto el problema. Hay tres mecanismos para forzar al modelo a devolver JSON con un schema fijo, y una librería ergonómica que los unifica. Veamos por qué importa, cómo funciona, y cómo lo aterrizamos en el `estimator`.

---

## Texto libre frente a JSON estructurado: el coste a largo plazo

![01-texto-libre-vs-json.jpg](https://media1-production-mightynetworks.imgix.net/asset/730d9b8f-5de2-4e8c-980b-59de3145ee1a/01-texto-libre-vs-json.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

El flujo de la izquierda es lo que tienes ahora. El LLM produce texto libre, alguien escribe un parser para extraer los datos que el frontend necesita, y el frontend los renderiza. El parser puede ser regex, puede ser otro LLM extractor, puede ser un parser de markdown. La cuestión no es qué herramienta uses, es que esa pieza no debería existir.

Cada vez que el modelo cambia ligeramente cómo formatea la respuesta —porque has actualizado el prompt, porque has cambiado de proveedor, porque el modelo ha tenido una actualización— el parser es susceptible de romperse. Y los fallos del parser son los peores: silenciosos. Los datos llegan al frontend deformados, la tabla se renderiza con un campo vacío, nadie se entera hasta que un usuario reporta que la estimación dice cero euros.

El flujo de la derecha invierte la lógica. En lugar de adivinar qué ha devuelto el modelo, le **dices al modelo qué tiene que devolver**. Defines el shape exacto de la respuesta como un schema, lo envías al modelo como parte del contrato de la llamada, y el proveedor garantiza que la respuesta cumple ese schema. La validación es trivial porque el JSON ya viene con la forma correcta, y si por algún motivo no la cumpliera, el error es explícito y temprano: una excepción de validación, no un campo vacío en la UI.

El cambio de mentalidad es: el LLM deja de ser una caja que produce texto libre y pasa a ser una **función con tipo de retorno**. Igual que cualquier endpoint REST de tu aplicación tiene un schema de respuesta documentado, la llamada al LLM lo tiene también. Lo único que hay que aprender es cómo se pasa ese schema a cada proveedor.

---

## El JSON Schema como contrato (y Pydantic como pieza central)

Antes de mirar el código, conviene fijar la mecánica. La idea base es que **el schema viaja con la petición**. Cuando llamas al modelo, además del prompt, le pasas un objeto JSON Schema que describe la forma exacta de la respuesta esperada: qué campos hay, qué tipos, cuáles son obligatorios, qué valores admite cada enum.

JSON Schema es un estándar de la industria que existe desde mucho antes que los LLMs. Se usa en OpenAPI, en validadores de configuración, en pipelines de datos. Si nunca lo has visto en detalle, la [introducción oficial](https://json-schema.org/learn/getting-started-step-by-step) cubre lo que necesitas en quince minutos: tipos básicos, propiedades requeridas, enums, objetos anidados.

Lo que cambia las cosas en Python es que **no hace falta escribir el JSON Schema a mano**. Pydantic lo genera automáticamente a partir de un modelo. Tú escribes una clase como esta:

```python
from pydantic import BaseModel, Field

class Phase(BaseModel):
    name: str
    duration_weeks: int = Field(ge=1, le=52)
    cost_eur: int = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    assumptions: list[str]

class EstimationResult(BaseModel):
    summary: str
    total_duration_weeks: int = Field(ge=1)
    total_cost_eur: int = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    phases: list[Phase]

```

Y Pydantic te da el JSON Schema con `EstimationResult.model_json_schema()`. Si vienes de Rails, esto es lo más cercano a `ActiveModel::Serializers` que has visto: una sola declaración produce a la vez la clase Python con tipos y validación, el schema JSON para el LLM, y la documentación OpenAPI cuando expones el endpoint. Es la pieza que sostiene todo el bloque.

Pydantic también te permite añadir **validadores** custom para reglas de negocio que el JSON Schema no expresa directamente, como [está documentado en su guía](https://docs.pydantic.dev/latest/concepts/validators/):

```python
from pydantic import model_validator

class EstimationResult(BaseModel):
    summary: str
    total_duration_weeks: int = Field(ge=1)
    total_cost_eur: int = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    phases: list[Phase]

    @model_validator(mode="after")
    def total_must_match_sum_of_phases(self):
        sum_weeks = sum(p.duration_weeks for p in self.phases)
        sum_cost = sum(p.cost_eur for p in self.phases)
        if abs(sum_weeks - self.total_duration_weeks) > 1:
            raise ValueError("total_duration_weeks does not match phases")
        if abs(sum_cost - self.total_cost_eur) / self.total_cost_eur > 0.05:
            raise ValueError("total_cost_eur does not match phases")
        return self

```

Esto es importante porque en el siguiente bloque hablaremos de guardrails, y los validadores de Pydantic son una de las dos formas de implementarlos. Aquí los menciono para que veas que el schema no se queda en estructura: cubre también coherencia interna.

El ciclo completo, una vez tienes el modelo definido, es éste:

![02-ciclo-pydantic.jpg](https://media1-production-mightynetworks.imgix.net/asset/d36e26a7-7632-451b-9fd9-24b3bd3f22bd/02-ciclo-pydantic.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

Lo defines una vez, lo usas tres veces. La definición es el contrato con el LLM, la documentación de la API REST que expones al cliente, y el tipo de la variable que pasea por tu código. Es el clásico *single source of truth*, pero aplicado a la frontera entre tu aplicación y el modelo.

---

## Tres caminos al mismo sitio

Cuando vas a forzar la salida estructurada, te vas a encontrar tres mecanismos según el proveedor. No son tres APIs distintas que aprender, son tres formas de empaquetar la misma idea.

![03-tres-caminos.jpg](https://media1-production-mightynetworks.imgix.net/asset/ada1879d-ce8d-4b9e-a61d-558870b3a31a/03-tres-caminos.jpg?ixlib=rails-4.3.1&fm=jpg&q=75&auto=format&w=1400&h=1400&fit=max&impolicy=ResizeCrop&constraint=downsize&aspect=fit)

**OpenAI: Structured Outputs (vía nativa).** Esto es lo que [OpenAI presentó como Structured Outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/) en 2024 y documenta en la [guía técnica oficial](https://platform.openai.com/docs/guides/structured-outputs). Tú pasas el modelo Pydantic en el parámetro `text_format` de Responses API (o `response_format` en Chat Completions) y la API garantiza que la respuesta cumple el schema. Adherencia del 100%. Sin código de ejemplo aquí porque lo veremos abajo con Instructor por encima.

**Anthropic: tool use forzado (vía idiomática).** Anthropic no tiene un modo "structured outputs" con un parámetro propio. La forma idiomática, [documentada en su guía de tool use](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview), es definir una herramienta cuyo `input_schema` es el shape que quieres recibir, y forzar al modelo a llamar a esa herramienta con `tool_choice={"type": "tool", "name": "..."}`. La respuesta del modelo viene como una llamada a esa herramienta cuyo `input` es exactamente el JSON con el shape que pediste. Conceptualmente es lo mismo que OpenAI Structured Outputs, solo que empaquetado con la primitiva que Anthropic eligió como universal. Si pruebas Claude desde la API directa, la mecánica está bien, pero el código que tienes que escribir difiere del de OpenAI.

**Otros proveedores: vía agregador.** Mistral, Gemini, DeepSeek y los modelos locales tienen cada uno su mecanismo, con grados de soporte variables. La forma sensata de tratar con esto es usar un agregador como [LiteLLM](https://docs.litellm.ai/) que normaliza las APIs, lo que ya hicimos en la sesión 03 al construir el wrapper de proveedores.

Aquí entra **Instructor**. Es la librería de [Jason Liu](https://python.useinstructor.com/) que coge tu modelo Pydantic, detecta qué proveedor estás usando, y empaqueta la llamada con el mecanismo correcto: Structured Outputs si es OpenAI, tool use forzado si es Anthropic, lo que toque si es vía LiteLLM. La interfaz que ves desde tu código es siempre la misma, y la respuesta es siempre una instancia tipada de tu modelo Pydantic. Es la abstracción que va a vivir en el `estimator` y la que recomendamos para el proyecto.

```python
import instructor
from openai import OpenAI

from app.schemas import EstimationResult

client = instructor.from_openai(OpenAI())

result = client.chat.completions.create(
    model="gpt-4o-mini",
    response_model=EstimationResult,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
)

# result is already an EstimationResult instance, no JSON parsing needed.
print(result.total_cost_eur)

```

El cambio relevante respecto al código que tenías al final del ejercicio previo está en dos sitios: envuelves el cliente con `instructor.from_openai(...)`, y añades `response_model=EstimationResult` a la llamada. El retorno deja de ser un objeto de respuesta del SDK y pasa a ser directamente la instancia de tu modelo. Si el LLM devuelve algo que no respeta el schema, Instructor reintenta automáticamente unas cuantas veces antes de darse por vencido y lanzar una excepción.

Cambiar de proveedor con esta abstracción es una línea: `instructor.from_anthropic(Anthropic())`. El `EstimationResult` se queda donde está, los prompts se quedan donde están, el resto del código no se entera.

---

## Refactor del `estimator`

Con la pieza nueva en la mano, el endpoint del servicio IA queda así:

```python
import instructor
from fastapi import FastAPI
from openai import OpenAI

from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse, EstimationResult

app = FastAPI()
client = instructor.from_openai(OpenAI())

@app.post("/estimate")
def estimate(request: EstimationRequest) -> EstimationResponse:
    system, user = render_estimation_prompt(request)

    result: EstimationResult = client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=EstimationResult,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    return EstimationResponse(
        result=result,
        prompt_version="v1",
    )

```

Y el `EstimationResponse` ahora encapsula el resultado tipado:

```python
class EstimationResponse(BaseModel):
    result: EstimationResult
    prompt_version: str

```

El cliente recibe un JSON con la forma exacta de `EstimationResponse`, el frontend tiene autocompletado completo si trabajas en TypeScript con un cliente generado, y la presentación se vuelve directa. Si el formulario pidió `phases_table`, el componente itera sobre `result.phases` y monta la tabla. Si pidió `narrative`, renderiza `result.summary` con el formato que prefiera. La presentación es responsabilidad del frontend, los datos son siempre los mismos.

Una decisión arquitectónica que conviene fijar: **el servicio IA siempre devuelve el shape rico**, no la presentación. El `output_format` del `EstimationRequest` es una pista que el prompt usa para que el modelo produzca un summary más o menos extenso, o asunciones más detalladas en cada fase, pero el schema que sale del servicio es siempre `EstimationResult`. La elección de cómo se presenta esa estructura al usuario vive en el backend de negocio o en el frontend, no en el servicio IA. Eso te da algo importante: si mañana añades otra forma de presentar la estimación (un PDF, un slack message, una notificación por email), no tocas el servicio IA. La frontera entre datos y presentación queda limpia.

Como en los bloques anteriores, este refactor se acompaña de tests. El test del schema es trivial pero importante:

```python
def test_estimation_result_total_cost_must_match_phases():
    result = EstimationResult(
        summary="Test",
        total_duration_weeks=10,
        total_cost_eur=10000,
        confidence_pct=80,
        phases=[
            Phase(name="Design", duration_weeks=4, cost_eur=4000,
                  confidence_pct=90, assumptions=[]),
            Phase(name="Build", duration_weeks=6, cost_eur=8000,
                  confidence_pct=70, assumptions=[]),
        ],
    )
    # 4000 + 8000 = 12000, but total says 10000 -> should fail
    # the model_validator we defined above

```

No probamos el LLM, probamos el contrato. Cuando alguien añada un campo nuevo o cambie una constraint, el test te avisa.

---

## Una nota sobre stacks que no son Python

El patrón es independiente del lenguaje, pero la ergonomía no. En Ruby, la combinación más cercana a Pydantic + Instructor es `dry-struct` (o `dry-validation`) para definir el schema y la gema `ruby-openai` llamando al endpoint con `response_format` configurado a JSON Schema. El JSON Schema lo tienes que escribir a mano o generarlo con una helper, no hay un equivalente directo a `model_json_schema()`. En PHP/Laravel, `spatie/laravel-data` hace algo parecido: define DTOs tipados de los que se puede derivar un schema, aunque la integración con LLMs requiere más trabajo manual.

En todos los casos el patrón es el mismo: definir el shape, traducirlo a JSON Schema, pasárselo al LLM, validar al volver. Lo que cambia es la cantidad de boilerplate y la robustez de las librerías de validación. Esta es una de las razones por las que el programa elige Python para el servicio IA: en este bloque concreto, la diferencia de ergonomía con otros stacks es notable.

---

## Qué haremos en la sesión en vivo

Llegarás a la sesión con el marco mental para responder por qué un producto serio no consume texto libre del LLM, sino datos con shape fijo, y con el `estimator` ya estructurado a nivel de prompt y de formulario.

En la sesión:

- Implementaremos juntos `EstimationResult` con varios niveles de complejidad (campos opcionales, anidados, listas), y discutiremos cuándo conviene un schema rico y cuándo uno minimal.

- Veremos en directo la diferencia entre OpenAI Structured Outputs y Anthropic tool use en código, sin Instructor por medio, para entender lo que la abstracción nos está ahorrando.

- Conectaremos Instructor con LiteLLM y haremos pruebas con varios modelos para ver cómo de portable es el código.

- Tocaremos los retries automáticos de Instructor y discutiremos cuándo aumentar el número de intentos y cuándo es síntoma de que el prompt está pidiendo algo imposible.

- Sentaremos la base para los siguientes temas: una vez tienes JSON validado contra schema, los guardrails se construyen en parte como validadores de Pydantic y en parte como capas adicionales sobre el contenido. Lo veremos en el siguiente bloque.

---

## Recursos de este bloque

**Lecturas complementarias antes de la sesión:**

- OpenAI — [Introducing Structured Outputs in the API](https://openai.com/index/introducing-structured-outputs-in-the-api/)

- OpenAI — [Structured Outputs (guía técnica)](https://platform.openai.com/docs/guides/structured-outputs)

- Anthropic — [Tool use overview](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview)

- Pydantic — [Models](https://docs.pydantic.dev/latest/concepts/models/)

- Pydantic — [Validators](https://docs.pydantic.dev/latest/concepts/validators/)

- Instructor — [Documentación oficial](https://python.useinstructor.com/)

- OpenAI Cookbook — [Introduction to Structured Outputs](https://developers.openai.com/cookbook/examples/structured_outputs_intro)

- Simon Willison — [OpenAI: Introducing Structured Outputs in the API](https://simonwillison.net/2024/Aug/6/openai-structured-outputs/)

- Jason Liu en Latent Space — [High Agency Pydantic > VC Backed Frameworks](https://www.latent.space/p/instructor)

- JSON Schema — [Getting Started Step-By-Step](https://json-schema.org/learn/getting-started-step-by-step)
