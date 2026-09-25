# Plan de implementación: Agente de contenido Instagram de RC Farias

> **Para quién es este documento:** para cualquier modelo o desarrollador que vaya a construir el agente. Es autocontenido: define el objetivo, la arquitectura, los contratos de datos, los prompts, las reglas de validación, el flujo de ejecución y los criterios de aceptación. Si algo no está aquí, **no lo inventes**: déjalo como `TODO` y repórtalo.

---

## 0. Resumen ejecutivo

| Aspecto | Decisión |
|---|---|
| Qué produce | 4 piezas de Instagram al mes: **2 carruseles + 2 reels** (una por semana del mes siguiente) |
| Cuándo | Automáticamente el **día 15 de cada mes** |
| Dónde corre | **GitHub Actions** (cron), sin servidores |
| LLM | **API de Anthropic (Claude)** con la herramienta de servidor `web_search` para investigar tendencias reales |
| Selección de temas | La hace el agente: el **código** rota los pilares y tipos de forma determinista, y el **modelo** propone el ángulo concreto |
| Historial | `data/historial.jsonl` dentro del repo, versionado en git |
| Entrega | Correo a **contenido.rcfarias@gmail.com** (SMTP de Gmail, librería estándar de Python) |
| Dependencias de terceros | **Una sola librería**: `anthropic` (SDK oficial). Todo lo demás usa la librería estándar de Python |
| Llamadas al LLM por mes | **1 llamada principal** (con búsqueda web) y **0–2 llamadas de reparación** baratas (sin búsqueda), solo si la validación falla |

---

## 1. Objetivo de negocio (léelo antes de programar)

RC Farias es una agencia BTL colombiana, miembro de Constellation, especializada en experiencias de marca para grandes empresas. El agente existe para que **cada mes haya contenido educativo, diferenciado y basado en datos reales** para gerentes de marca y mercadeo, **sin repetir** tendencias ni estrategias ya publicadas y con un costo operativo mínimo.

Implicaciones para el diseño:
1. **La veracidad importa más que la creatividad.** Cada pieza debe apoyarse en una fuente real, con URL y fecha, que se pueda verificar.
2. **No repetir es un requisito duro.** Se controla por dos vías: el prompt (el modelo ve el historial) y el código (una validación determinista de similitud).
3. **Siempre hay revisión humana antes de publicar.** El agente entrega por correo y no publica en Instagram.

---

## 2. Principios de diseño (restricciones no negociables)

1. **Mínima dependencia de terceros**
   - Python ≥ 3.11 y solo la librería estándar (`json`, `smtplib`, `email`, `unicodedata`, `re`, `string`, `datetime`, `pathlib`, `unittest`, `argparse`, `logging`).
   - Única dependencia externa: `anthropic`, con la versión fijada en `requirements.txt`.
   - Nada de LangChain, frameworks de agentes, bases de datos, pytest, Jinja, pydantic, requests ni schedulers externos.
2. **Mínimo cómputo**
   - **Una sola llamada** genera las 4 piezas. El historial y las instrucciones viajan una sola vez, y el modelo puede garantizar que las 4 piezas no se parezcan entre sí.
   - Todo lo que se puede decidir con código se decide con código: rotación de pilares, conteo de palabras, hashtags prohibidos, años, CTA y duplicados. El LLM solo investiga y redacta.
   - La reparación es **quirúrgica**: solo se reenvía la pieza que falló, **sin** búsqueda web.
   - `web_search` va con un `max_uses` acotado (6).
   - **Sin prompt caching.** Con una llamada al mes no aporta nada; no lo implementes.
3. **Determinismo e idempotencia**
   - Si ya existe `salidas/AAAA-MM/piezas.json` para el mes objetivo, el agente no vuelve a generar, salvo que se use `--forzar`.
   - Hay un modo `--simular` (dry-run) que no llama a la API, no envía correo y no escribe el historial.
4. **Fallar de forma visible, nunca en silencio**
   - Si una pieza sigue inválida después de las reparaciones, se entrega igual, marcada con `⚠️ REVISAR` y la lista de errores.
   - Si la llamada principal falla del todo, el job de GitHub Actions termina en rojo y GitHub avisa por correo al dueño del repo.

---

## 3. Arquitectura

```
┌───────────────────────── GitHub Actions (cron día 15) ─────────────────────────┐
│                                                                                 │
│  1. planificador.py  → decide 4 “slots” (semana, formato, tipo, pilar)          │
│         │               rotando lo menos usado según data/historial.jsonl       │
│         ▼                                                                       │
│  2. prompts.py       → arma system + user (historial compacto + slots)          │
│         ▼                                                                       │
│  3. generador.py     → 1 llamada a Claude con web_search + JSON schema          │
│         │               (maneja pause_turn, refusal, max_tokens)                │
│         ▼                                                                       │
│  4. validador.py     → reglas deterministas por pieza                           │
│         │  ├─ OK → sigue                                                        │
│         │  └─ FALLA → generador.reparar(pieza, errores) sin web_search (≤2)     │
│         ▼                                                                       │
│  5. salidas/AAAA-MM/ → piezas.json + piezas.md + respuesta_cruda.json           │
│  6. correo.py        → envía piezas.md a contenido.rcfarias@gmail.com           │
│  7. historial.py     → agrega 4 líneas a data/historial.jsonl                   │
│  8. workflow         → git commit + push (historial y salidas)                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Estructura de archivos

```
.
├── PLAN.md                          ← este documento
├── README.md                        ← cómo configurar secretos y correr local
├── requirements.txt                 ← solo: anthropic==<versión fijada>
├── .github/workflows/contenido-mensual.yml
├── config/
│   ├── pilares.json                 ← pilares y tipos (editable por el equipo)
│   └── ajustes.json                 ← modelo, effort, max_uses, destinatario, etc.
├── prompts/
│   ├── sistema.md                   ← prompt de sistema (plantilla string.Template)
│   ├── usuario.md                   ← prompt de usuario (plantilla string.Template)
│   └── reparacion.md                ← prompt de reparación
├── agente/
│   ├── __init__.py
│   ├── __main__.py                  ← CLI: python -m agente [--mes AAAA-MM] [--forzar] [--simular] [--sin-correo]
│   ├── config.py                    ← carga config/*.json y variables de entorno
│   ├── planificador.py
│   ├── prompts.py
│   ├── esquema.py                   ← JSON Schema de salida (dict de Python)
│   ├── generador.py
│   ├── validador.py
│   ├── historial.py
│   ├── render.py                    ← piezas.json → piezas.md (texto del correo)
│   └── correo.py
├── data/
│   └── historial.jsonl              ← una pieza por línea (append-only)
├── salidas/
│   └── AAAA-MM/{piezas.json, piezas.md, respuesta_cruda.json}
└── tests/
    ├── fixtures/respuesta_ejemplo.json
    ├── test_validador.py
    ├── test_planificador.py
    └── test_render.py
```

---

## 4. Configuración

### 4.1 `config/ajustes.json`

```json
{
  "modelo": "claude-opus-5",
  "effort": "medium",
  "max_tokens": 32000,
  "web_search_max_uses": 6,
  "max_reparaciones": 2,
  "destinatario": "contenido.rcfarias@gmail.com",
  "zona_horaria": "America/Bogota",
  "umbral_similitud": 0.5,
  "antiguedad_max_fuente_meses": 18,
  "calendario": [
    {"semana": 1, "formato": "Carrusel"},
    {"semana": 2, "formato": "Reel"},
    {"semana": 3, "formato": "Carrusel"},
    {"semana": 4, "formato": "Reel"}
  ]
}
```

- El `modelo` se puede cambiar sin tocar código. Referencia de precios de la documentación de Anthropic (caché del 24/06/2026, conviene verificarla en la página oficial de precios antes de decidir):
  - `claude-opus-5`: USD 5 / 25 por millón de tokens de entrada / salida (valor por defecto).
  - `claude-sonnet-5`: USD 2 / 10, alternativa más barata.
  - `web_search`: USD 10 por cada 1.000 búsquedas.

  **Cambiar de modelo es una decisión de negocio (calidad vs. costo) del equipo de RC, no del implementador.**
- `effort: "medium"` equilibra calidad y consumo. Solo vale la pena subirlo a `high` si la calidad medida no alcanza.

### 4.2 `config/pilares.json` (propuesta inicial, el equipo de RC debe validarla)

```json
{
  "pilares": [
    "Activaciones de marca y experiencias en vivo",
    "Eventos corporativos y lanzamientos de producto",
    "Trade marketing y experiencia en punto de venta",
    "Medición y data de experiencias (ROI de BTL)",
    "Tecnología aplicada a experiencias (inmersivo, phygital)",
    "Sampling y prueba de producto",
    "Sostenibilidad en producción de eventos",
    "Estrategia de marca y comportamiento del consumidor"
  ],
  "tipos": ["Educativo", "Tendencia", "Mito vs. realidad", "Checklist / cómo hacerlo"]
}
```

> ⚠️ **Supuesto:** el campo “Tipo” del flujo original no estaba definido. Esta lista es una propuesta y **debe confirmarla el equipo**.

### 4.3 Secretos (GitHub → Settings → Secrets and variables → Actions)

| Secreto | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | Llamadas a Claude |
| `GMAIL_USER` | Cuenta remitente (puede ser la misma contenido.rcfarias@gmail.com) |
| `GMAIL_APP_PASSWORD` | “Contraseña de aplicación” de Google (requiere verificación en 2 pasos activa). **Nunca** la contraseña normal |

Ningún secreto debe escribirse en logs, archivos ni commits.

---

## 5. Contratos de datos

### 5.1 Historial: `data/historial.jsonl`

Una línea JSON por pieza generada:

```json
{"id":"2026-10-S1","fecha_generacion":"2026-09-15","mes_objetivo":"2026-10","semana":1,"formato":"Carrusel","tipo":"Educativo","pilar":"Trade marketing y experiencia en punto de venta","tema_especifico":"...","tendencia":"...","estrategia_clave":"...","fuente_url":"https://...","estado":"generado"}
```

- `estado` puede ser `generado`, `publicado` o `descartado`. El agente escribe `generado`. El equipo puede editarlo a mano, directamente en GitHub, a `publicado` o `descartado`.
- **Las piezas `descartado` no cuentan** como “ya usadas” para la regla de no repetir. Las demás sí.
- Historial compacto para el prompt: solo `mes_objetivo | pilar | tendencia | estrategia_clave`, una línea por pieza (unos 40 tokens por pieza, unos 2.000 tokens por año). **Se envía completo**: el volumen es trivial y la regla de no repetir exige el historial entero.
- Si hay historial previo (el antiguo `{{13.historia}}` de Make), se migra una vez a este formato con `estado: "publicado"`.

### 5.2 Salida del modelo: JSON Schema (`agente/esquema.py`)

Se usa **structured outputs** (`output_config.format` de tipo `json_schema`). Restricciones que la API no soporta y que se validan en `validador.py`: longitud exacta del array (4 piezas), conteo de palabras y cantidad de hashtags.

```python
INVESTIGACION = {
    "type": "object",
    "properties": {
        "tendencia": {"type": "string"},          # nombre corto de la tendencia/estrategia
        "resumen": {"type": "string"},            # 2-3 líneas con datos verificables
        "estrategia_clave": {"type": "string"},   # 1 frase: qué se recomienda hacer
        "fuente_titulo": {"type": "string"},
        "fuente_url": {"type": "string"},
        "fuente_fecha": {"type": "string"}        # AAAA-MM-DD, AAAA-MM o "sin fecha visible"
    },
    "required": ["tendencia", "resumen", "estrategia_clave", "fuente_titulo", "fuente_url", "fuente_fecha"],
    "additionalProperties": False
}

COMUNES = {  # se fusionan en ambos tipos de pieza
    "semana": {"type": "integer"},
    "tipo": {"type": "string"},
    "pilar": {"type": "string"},
    "tema_especifico": {"type": "string"},
    "investigacion": INVESTIGACION,
    "caption": {"type": "string"},
    "cta": {"type": "string"},
    "hashtags": {"type": "array", "items": {"type": "string"}}
}

CARRUSEL = {
    "type": "object",
    "properties": {**COMUNES,
        "formato": {"type": "string", "enum": ["Carrusel"]},
        "slide_1_gancho": {"type": "string"},
        "slide_2": {"type": "string"},
        "slide_3": {"type": "string"},
        "slide_4": {"type": "string"},
        "slide_5_cierre": {"type": "string"}},
    "required": [*COMUNES, "formato", "slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre"],
    "additionalProperties": False
}

REEL = {
    "type": "object",
    "properties": {**COMUNES,
        "formato": {"type": "string", "enum": ["Reel"]},
        "escena_1_gancho": {"type": "string"},      # 0-5 s
        "escena_2_desarrollo_a": {"type": "string"}, # 5-12 s
        "escena_3_desarrollo_b": {"type": "string"}, # 12-20 s
        "escena_4_desarrollo_c": {"type": "string"}, # 20-25 s
        "escena_5_cta": {"type": "string"}},         # 25-30 s
    "required": [*COMUNES, "formato", "escena_1_gancho", "escena_2_desarrollo_a",
                 "escena_3_desarrollo_b", "escena_4_desarrollo_c", "escena_5_cta"],
    "additionalProperties": False
}

ESQUEMA = {
    "type": "object",
    "properties": {"piezas": {"type": "array", "items": {"anyOf": [CARRUSEL, REEL]}}},
    "required": ["piezas"],
    "additionalProperties": False
}

ESQUEMA_PIEZA = {"anyOf": [CARRUSEL, REEL]}  # usado en reparación (envolver en objeto {"pieza": ...})
```

> ⚠️ **Riesgo técnico por verificar en la Fase 1:** la documentación indica que structured outputs es incompatible con *citations* de documentos. **No está confirmado** si lo es con las citas que genera `web_search`.
> - Primera tarea de la Fase 1: hacer una llamada de prueba con `web_search` + `output_config.format`.
> - **Plan B** si devuelve 400: quitar `output_config.format`, pedir en el prompt “responde solo con un bloque JSON que cumpla este esquema” (pegando el esquema) y parsear localmente el último bloque de texto con `json.loads`. `validador.py` ya cubre la validación estructural, así que el resto del diseño no cambia.

---

## 6. Prompts

Las plantillas usan `string.Template` (`$variable`). Las variables se insertan **ya formateadas** por `prompts.py`.

### 6.1 `prompts/sistema.md`

```
Eres el estratega de contenido de RC Farias, agencia BTL colombiana miembro de Constellation,
especializada en experiencias de marca memorables para grandes empresas.

AUDIENCIA: gerentes de marca y mercadeo de empresas medianas y grandes.
TONO: educativo, profesional y directo.
VOZ: habla desde RC Farias en primera persona plural: creamos / ejecutamos / diseñamos.

REGLAS DURAS (se validan automáticamente; si no se cumplen, la pieza se rechaza):
- Nunca uses años específicos (p. ej. 2025, 2026) en slides, escenas ni captions. Deben ser atemporales.
- Prohibidos los hashtags #viral #explore #trending #fyp y cualquier hashtag genérico de relleno.
- El caption debe terminar EXACTAMENTE con: 📲 Síguenos para más ideas que conectan data, experiencia y negocio.
  Ese texto también va en el campo "cta".
- Nunca repitas tendencias ni estrategias que aparezcan en el HISTORIAL, ni entre las piezas de esta entrega.

INVESTIGACIÓN (obligatoria para cada pieza):
- Usa la herramienta de búsqueda web. No respondas de memoria.
- Por pieza, identifica 1 tendencia o estrategia ACTUAL y REAL sobre el pilar indicado.
- Resúmela en 2-3 líneas con datos verificables (cifra, estudio o caso concreto).
- Reporta la fuente exacta que usaste: título, URL y fecha de publicación (o "sin fecha visible").
- Prefiere fuentes primarias o de industria reconocidas y publicadas en los últimos 18 meses.
- Si no encuentras evidencia sólida, elige otra tendencia; nunca inventes datos ni URLs.

FORMATO CARRUSEL:
- slide_1_gancho: máximo 8 palabras. Afirmación provocadora o pregunta disruptiva.
- slide_2, slide_3, slide_4: contenido, máximo 30 palabras cada uno.
- slide_5_cierre: máximo 30 palabras. Debe mencionar "RC Farias" y "Constellation".
- hashtags: exactamente 3, en este orden:
  1) #RCFarias
  2) 1 de nicho de servicio real (BTL, activaciones, eventos, estrategia)
  3) 1 de comunidad/industria (marketing, marcas, trade)

FORMATO REEL (guion de 30 segundos; cada campo es el TEXTO EN PANTALLA):
- escena_1_gancho (0-5 s): máximo 6 palabras, afirmación provocadora.
- escena_2_desarrollo_a (5-12 s): máximo 8 palabras.
- escena_3_desarrollo_b (12-20 s): máximo 8 palabras.
- escena_4_desarrollo_c (20-25 s): máximo 8 palabras.
- escena_5_cta (25-30 s): máximo 6 palabras, llamada a la acción directa.
- hashtags: entre 3 y 5, el primero siempre #RCFarias.

CAPTION (ambos formatos): atemporal, sin años, cierra con el CTA obligatorio.

Responde únicamente con el JSON del esquema indicado.
```

### 6.2 `prompts/usuario.md`

```
HISTORIAL DE CONTENIDO PUBLICADO (no repetir estas tendencias ni estrategias):
$historial

Genera exactamente 4 piezas de Instagram, una por cada fila, en este orden:

$slots

Para cada pieza, propone un "tema_especifico" dentro del pilar asignado, investiga con búsqueda
web y redacta el contenido según el formato. Las 4 piezas deben tratar tendencias distintas entre sí.
```

- `$historial` son líneas `- AAAA-MM | pilar | tendencia | estrategia_clave`, o `(sin historial)`.
- `$slots` son líneas `- Semana 1 | Formato: Carrusel | Tipo: Educativo | Pilar: ...`.

### 6.3 `prompts/reparacion.md` (sin web_search)

```
La siguiente pieza no cumple las reglas. Corrige SOLO lo necesario para resolver los errores,
conservando la investigación, la fuente y el sentido del contenido. No cambies la tendencia.

ERRORES:
$errores

PIEZA:
$pieza_json
```

Se envía con el mismo prompt de sistema y `output_config.format` = `{"pieza": ESQUEMA_PIEZA}` (envuelto en un objeto con `additionalProperties: false`).

---

## 7. Lógica de cada módulo

### 7.1 `planificador.py`: rotación determinista (sin LLM)

Entradas: `pilares.json`, `ajustes.calendario` y el historial sin los `descartado`.

Para cada slot del calendario, en orden:
1. **Pilar:** el que tenga el uso más antiguo (los nunca usados van primero; si hay empate, gana el orden de `pilares.json`) y que no esté ya asignado este mes.
2. **Tipo:** el mismo criterio sobre `tipos`, con la restricción de que dos piezas del mismo formato no compartan tipo en el mes.

Salida: una lista de 4 dicts `{semana, formato, tipo, pilar}`. La función es **pura** (mismas entradas, misma salida) y tiene tests.

**Mes objetivo:** el mes siguiente a la fecha de ejecución, en `America/Bogota`. Si se ejecuta el 15/09, genera el contenido de octubre. Se puede sobrescribir con `--mes AAAA-MM`.

> ⚠️ **Supuesto:** el día 15 se genera el contenido **del mes siguiente**. Si la intención es otra, basta con cambiar una línea en `config.py`.

### 7.2 `generador.py`: llamada a la API

Parámetros de la llamada principal (SDK Python oficial, **streaming** porque la salida es larga):

```python
import anthropic
client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

params = dict(
    model=ajustes["modelo"],
    max_tokens=ajustes["max_tokens"],
    system=sistema,
    messages=[{"role": "user", "content": usuario}],
    tools=[{"type": "web_search_20260209", "name": "web_search",
            "max_uses": ajustes["web_search_max_uses"]}],
    output_config={"effort": ajustes["effort"],
                   "format": {"type": "json_schema", "schema": ESQUEMA}},
)
with client.messages.stream(**params) as stream:
    respuesta = stream.get_final_message()
```

Reglas obligatorias de implementación:
- **No** enviar `thinking` con `budget_tokens`, **ni** `temperature`/`top_p`, **ni** prefill de asistente: los modelos actuales responden 400. Con Opus 5, si se omite `thinking`, el modelo usa pensamiento adaptativo.
- **No** declarar `code_execution` junto a `web_search_20260209`, porque este ya incluye filtrado dinámico.
- Revisar `stop_reason` **antes** de leer el contenido:
  - `pause_turn`: volver a llamar agregando `{"role":"assistant","content": respuesta.content}` a los mensajes, **sin** añadir un mensaje de usuario tipo "continúa". Máximo 3 reanudaciones.
  - `refusal`: abortar con un error claro. El job queda en rojo.
  - `max_tokens`: reintentar una vez con `max_tokens` duplicado (tope 64000). Si vuelve a fallar, abortar.
  - `end_turn`: seguir.
- Extraer el JSON del **último** bloque `type == "text"` y hacer `json.loads`.
- Extraer todas las URLs de los bloques `web_search_tool_result`, donde `content` es una lista de resultados con `url`. Si `content` es un objeto con `error_code`, la búsqueda falló: registrarlo en el log.
- Guardar `respuesta.model_dump_json()` en `salidas/AAAA-MM/respuesta_cruda.json` para auditoría.
- Registrar `respuesta.usage` (tokens de entrada y salida, búsquedas) en el log y en `piezas.json` para medir el costo real.
- Manejo de errores del SDK, del más específico al más general: `anthropic.RateLimitError` → `anthropic.APIStatusError` → `anthropic.APIConnectionError`. El SDK ya reintenta 2 veces los errores 429/5xx; no hace falta sumar reintentos propios.
- (Opcional) Fallback por rechazo en el servidor: `client.beta.messages.stream(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Añade una dependencia de una función beta; actívalo solo si en la práctica aparecen rechazos.

`reparar(pieza, errores)`: igual que la llamada principal, pero **sin `tools`**, con `effort: "low"` y el esquema de una sola pieza.

### 7.3 `validador.py`: reglas deterministas (el corazón del control de calidad)

**Definición de “palabra”:** token separado por espacios que contiene al menos un carácter alfanumérico (`re.search(r"\w", token)`). Los emojis sueltos no cuentan.

| # | Regla | Aplica a | Severidad |
|---|---|---|---|
| V1 | Exactamente 4 piezas, semanas 1-4, formatos según el calendario | Entrega | Error |
| V2 | Slide 1 ≤ 8 palabras; slides 2-5 ≤ 30 palabras | Carrusel | Error |
| V3 | Slide 5 contiene “RC Farias” y “Constellation” (sin distinguir mayúsculas) | Carrusel | Error |
| V4 | Escenas 1 y 5 ≤ 6 palabras; escenas 2-4 ≤ 8 palabras | Reel | Error |
| V5 | Ningún año en slides, escenas ni caption: `\b(19\|20)\d{2}\b` | Ambos | Error |
| V6 | `cta` == texto exacto del CTA y el caption termina con él (tras `strip()`) | Ambos | Error |
| V7 | Hashtags: carrusel exactamente 3; reel entre 3 y 5; el primero es `#RCFarias`; sin duplicados; formato `^#\w+$` | Ambos | Error |
| V8 | Ningún hashtag en la lista negra: `#viral #explore #trending #fyp #instagood #love #follow #like4like` (comparación sin mayúsculas ni tildes). La lista es ampliable en `ajustes.json` | Ambos | Error |
| V9 | `fuente_url` empieza por `https://` y aparece entre las URLs devueltas por `web_search` en esta ejecución (comparación sin query string ni barra final) | Ambos | Error |
| V10 | Similitud con el historial y entre las piezas del mes < `umbral_similitud` (ver 7.4) | Ambos | Error |
| V11 | `fuente_fecha` interpretable y con antigüedad ≤ `antiguedad_max_fuente_meses`, o `"sin fecha visible"` | Ambos | **Advertencia** (se muestra en el correo y no dispara reparación) |
| V12 | `resumen` contiene al menos un número (indicio de dato verificable) | Ambos | Advertencia |

Salida: `{indice_pieza: {"errores": [...], "advertencias": [...]}}`.

> **Nota sobre V9:** es la defensa principal contra datos o URLs inventados, y no cuesta nada. Si una pieza falla V9, la reparación **no** puede corregirla porque no tiene búsqueda. En ese caso se marca como `⚠️ REVISAR: fuente no verificada` y no se intenta reparar.

### 7.4 Similitud anti-repetición (sin embeddings, sin dependencias)

1. Texto = `tendencia + " " + estrategia_clave`.
2. Normalizar: minúsculas, quitar tildes (`unicodedata.normalize("NFKD")` y descartar marcas combinantes), quitar puntuación y quitar stopwords españolas (una lista corta embebida en el código, de unas 60 palabras).
3. Jaccard sobre los conjuntos de palabras de cada texto.
4. Si el resultado es ≥ `umbral_similitud` (0,5) contra cualquier pieza del historial no descartada, o contra otra pieza del mes, la pieza es un duplicado.
5. Un duplicado **no se repara** (cambiar la tendencia exige una nueva búsqueda). Se entrega marcado `⚠️ REVISAR: posible repetición de <id del historial>`.

> Es una heurística barata que atrapa repeticiones obvias. La defensa principal sigue siendo el prompt. El umbral debe calibrarse con datos reales en la Fase 3.

### 7.5 `render.py`: `piezas.md` (cuerpo del correo)

Formato fijo y legible para copiar y pegar en Instagram o pasarlo al diseñador:

```
# Contenido Instagram RC Farias — Octubre (mes objetivo 2026-10)
Generado: 2026-09-15 · Modelo: claude-opus-5 · Costo estimado: USD 0,xx

## Semana 1 · Carrusel · Educativo
Pilar: … | Tema: …
### Investigación
Tendencia: …
Resumen: …
Fuente: <título> — <url> (fecha: …)
### Slides
SLIDE 1 (Gancho): …
SLIDE 2: …
…
### Caption
…
📲 Síguenos para más ideas que conectan data, experiencia y negocio.
### Hashtags
#RCFarias #… #…
⚠️ Advertencias: … (solo si hay)
---
```

(El encabezado del correo sí puede llevar el año; la regla de “sin años” aplica solo al contenido publicable.)

### 7.6 `correo.py`: envío con la librería estándar

- `smtplib.SMTP("smtp.gmail.com", 587)` + `starttls()` + `login(GMAIL_USER, GMAIL_APP_PASSWORD)`.
- `email.message.EmailMessage`: cuerpo en texto plano = `piezas.md`, con `piezas.json` y `piezas.md` adjuntos.
- Asunto: `Contenido IG RC Farias · <Mes objetivo>` y, si hay alguna pieza marcada, el prefijo `⚠️ REVISAR · `.
- Si el envío falla, se lanza una excepción y el job queda en rojo. Los archivos igual quedan commiteados, así que no se pierde nada.

> Verificar al implementar: Google exige verificación en 2 pasos para crear contraseñas de aplicación, y sus políticas cambian; confirmar en la ayuda de Google vigente.

### 7.7 `historial.py`

- `leer() -> list[dict]` (ignora líneas vacías y falla con un mensaje claro si hay JSON corrupto).
- `agregar(piezas, mes_objetivo)`: escribe 4 líneas con `estado: "generado"`. **Solo se ejecuta después del envío exitoso del correo**, para que un fallo no deje historial “fantasma”.

### 7.8 `__main__.py`: orquestación

```
1. Cargar config → resolver mes objetivo
2. Si existe salidas/<mes>/piezas.json y no --forzar → log "ya generado" y salir 0
3. slots = planificador.planificar(...)
4. Si --simular → imprimir prompts y slots, salir 0
5. resultado, urls = generador.generar(...)
6. informe = validador.validar(resultado, urls, historial)
7. Para cada pieza con errores reparables (V2-V8), hasta max_reparaciones:
       pieza = generador.reparar(pieza, errores); revalidar
8. Guardar salidas/<mes>/{piezas.json, piezas.md}
9. Si no --sin-correo → correo.enviar(...)
10. historial.agregar(...)
```

Códigos de salida: `0` si todo fue OK (aunque haya advertencias o piezas marcadas); `1` si hubo un error fatal (API, refusal, JSON inválido tras reintentos o fallo de correo).

---

## 8. GitHub Actions: `.github/workflows/contenido-mensual.yml`

```yaml
name: Contenido mensual Instagram

on:
  schedule:
    - cron: "17 12 15 * *"   # día 15, 12:17 UTC = 07:17 Bogotá (minuto no redondo: los cron en :00 suelen retrasarse)
  workflow_dispatch:
    inputs:
      mes:     { description: "Mes objetivo AAAA-MM (vacío = siguiente)", required: false }
      forzar:  { description: "Regenerar aunque exista", type: boolean, default: false }
      simular: { description: "Dry-run sin API ni correo", type: boolean, default: false }

permissions:
  contents: write

concurrency:
  group: contenido-mensual
  cancel-in-progress: false

jobs:
  generar:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements.txt
      - run: python -m unittest discover -s tests
      - name: Generar contenido
        env:
          ANTHROPIC_API_KEY:  ${{ secrets.ANTHROPIC_API_KEY }}
          GMAIL_USER:         ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: |
          ARGS=""
          [ -n "${{ inputs.mes }}" ] && ARGS="$ARGS --mes ${{ inputs.mes }}"
          [ "${{ inputs.forzar }}" = "true" ] && ARGS="$ARGS --forzar"
          [ "${{ inputs.simular }}" = "true" ] && ARGS="$ARGS --simular"
          python -m agente $ARGS
      - name: Guardar historial y salidas
        if: success() && inputs.simular != true
        run: |
          git config user.name  "rc-agente-contenido"
          git config user.email "actions@users.noreply.github.com"
          git add data/historial.jsonl salidas/
          git diff --cached --quiet || git commit -m "Contenido IG: $(date -u +%Y-%m)"
          git push
```

Consumo: alrededor de 1–3 minutos al mes de GitHub Actions, dentro de la cuota gratuita.

> Nota: GitHub desactiva los workflows programados de repos **públicos** tras 60 días sin actividad. Los commits mensuales del propio workflow mantienen la actividad, pero conviene verificarlo si el repo es público.

---

## 9. Plan de trabajo por fases (para el modelo implementador)

Cada fase termina con sus criterios cumplidos **antes** de pasar a la siguiente.

### Fase 1: Esqueleto y prueba de API (bloqueante)
- [ ] Estructura de carpetas, `requirements.txt` con `anthropic` fijado a la última versión estable, `config/*.json` y `prompts/*.md`.
- [ ] Script de prueba: una llamada con `web_search_20260209` + `output_config.format`. **Documentar en `README.md` si es compatible** o si se aplica el Plan B de la sección 5.2.
- ✅ Criterio: la prueba devuelve JSON parseable y las URLs de búsqueda se extraen correctamente.

### Fase 2: Lógica determinista (sin API)
- [ ] `planificador.py`, `validador.py`, `historial.py`, `render.py`, con tests `unittest` y fixtures.
- [ ] Tests mínimos:
  - Rotación de pilares con historial vacío, parcial y completo.
  - Cada regla V1-V12, con un caso que pasa y otro que falla.
  - Conteo de palabras con emojis y signos.
  - Detección de años.
  - Similitud con textos casi idénticos y con textos distintos.
- ✅ Criterio: `python -m unittest discover -s tests` en verde y sin red.

### Fase 3: Generación de punta a punta local
- [ ] `generador.py` (con `pause_turn`, `refusal` y `max_tokens`), el bucle de reparación y `__main__.py`.
- [ ] Ejecutar `python -m agente --mes <mes> --sin-correo` 2-3 veces y revisar a mano la calidad, la veracidad de las fuentes (abrir las URLs) y el costo registrado en `usage`.
- [ ] Calibrar `umbral_similitud` y `effort` con esas ejecuciones.
- ✅ Criterio: 4 piezas válidas; fuentes que existen y dicen lo que el resumen afirma; costo por ejecución registrado.

### Fase 4: Correo y automatización
- [ ] `correo.py` y el workflow de GitHub Actions.
- [ ] Ejecutar con `workflow_dispatch` en modo simular y luego en modo real.
- ✅ Criterio: el correo llega a contenido.rcfarias@gmail.com, se ve bien en Gmail web y móvil, y el historial queda commiteado.

### Fase 5: Migración del historial
- [ ] Convertir el historial existente (de Make u otra fuente) a `data/historial.jsonl` con `estado: "publicado"`.
- ✅ Criterio: el planificador y la regla V10 lo consideran correctamente.

---

## 10. Criterios de aceptación globales

1. El día 15, sin intervención humana, llega un correo con 4 piezas (2 carruseles y 2 reels) para el mes siguiente.
2. Todas las piezas cumplen V1-V10, o vienen marcadas explícitamente con `⚠️ REVISAR` y el motivo.
3. Cada pieza trae una fuente real (URL devuelta por la búsqueda) con su fecha.
4. Ninguna pieza repite una tendencia o estrategia del historial, según el prompt y V10.
5. La única dependencia externa es `anthropic`.
6. Ejecutar dos veces el mismo mes no duplica contenido ni historial.
7. Ningún secreto aparece en logs, archivos ni commits.

---

## 11. Estimación de costo mensual (estimación, no medición)

| Concepto | Supuesto | Costo aprox. |
|---|---|---|
| Entrada (prompt, historial y resultados de búsqueda) | ~40.000 tokens × USD 5/M | ~USD 0,20 |
| Salida (4 piezas y pensamiento adaptativo) | ~8.000 tokens × USD 25/M | ~USD 0,20 |
| Búsquedas web | ≤ 6 × USD 0,01 | ≤ USD 0,06 |
| Reparaciones (si ocurren) | ~5.000 tokens c/u | ~USD 0,05 c/u |
| GitHub Actions | ~3 min/mes | USD 0 (cuota gratuita) |
| **Total** | | **≈ USD 0,5 por mes con claude-opus-5** |

Los precios salen de la documentación de Anthropic (caché del 24/06/2026) y los volúmenes de tokens son supuestos. **El costo real debe medirse en la Fase 3** con `respuesta.usage`.

---

## 12. Supuestos tomados (confirmar con RC Farias)

1. El día 15 se genera el contenido del **mes siguiente**, una pieza por semana y en el orden Carrusel, Reel, Carrusel, Reel.
2. La lista de **pilares y tipos** (sección 4.2) es una propuesta.
3. El historial registra lo **generado**; el equipo marca a mano `publicado` o `descartado`.
4. El agente **no publica** en Instagram: solo entrega por correo para revisión humana.
5. Carrusel con exactamente 3 hashtags y reel con 3 a 5, tal como indica la especificación original (la diferencia parece intencional, pero conviene confirmarla).

---

## 13. Mejoras recomendadas (fuera del alcance mínimo, ordenadas por impacto)

1. **Cerrar el ciclo con métricas.** Agregar a `historial.jsonl` campos opcionales como `alcance`, `guardados` y `compartidos`, que el equipo llena a mano o con una exportación mensual. El planificador puede priorizar los pilares que mejor rinden. Así el contenido se optimiza por resultados y no solo por rotación.
2. **Brief visual por pieza.** Un campo `nota_visual` por slide o escena (qué mostrar y qué B-roll usar) ahorra una ronda con el diseñador o editor. Cuesta unos pocos cientos de tokens más.
3. **Aprobación en un clic.** Un `workflow_dispatch` “marcar publicado” que cambie `estado` sin editar el JSONL a mano, para reducir errores en el historial.
4. **Casos propios de RC.** Un archivo `config/casos_rc.md` con 5-10 casos reales de la agencia, que el modelo pueda citar en el slide de cierre. Hoy el contenido es genérico de la industria y no demuestra la experiencia propia, que es lo que convierte a un gerente de marca en cliente.
5. **Batch API (−50 % de costo).** No se recomienda por ahora: con unos USD 0,5 al mes el ahorro es marginal y añade complejidad (sondeo asíncrono). Además, falta verificar su compatibilidad con `web_search`.

---

## 14. Fuentes consultadas

- Documentación de la API de Anthropic, incluida en la skill `claude-api` de Claude Code (caché con fecha **24/06/2026**): IDs y precios de modelos, `web_search_20260209`, structured outputs (`output_config.format`) y sus incompatibilidades, manejo de `pause_turn` y `refusal`, parámetro `effort` y precio de búsqueda web (USD 10 por 1.000). **Verificar contra la documentación oficial vigente al implementar.**
- Configuración SMTP de Gmail y contraseñas de aplicación: **de conocimiento general, no verificado en esta sesión**. Confirmar en la ayuda oficial de Google.
- Comportamiento de cron y de desactivación por inactividad de GitHub Actions: **de conocimiento general, no verificado en esta sesión**. Confirmar en docs.github.com.
