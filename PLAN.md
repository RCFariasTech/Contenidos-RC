# Plan de implementación: Web app de contenido Instagram de RC Farias

> **Para quién es este documento:** cualquier modelo o desarrollador que vaya a construir la app. Es autocontenido: objetivo, arquitectura, modelo de datos, pantallas, API, prompts, reglas de validación, especificación del PowerPoint, fases y criterios de aceptación. Si algo no está aquí, **no lo inventes**: déjalo como `TODO` y repórtalo.
>
> **Versión 2:** reemplaza el diseño anterior basado en correo. No hay envío ni lectura de correos.

---

## 0. Resumen ejecutivo

| Aspecto | Decisión |
|---|---|
| Qué es | Web app privada (un único usuario) para generar, revisar, ajustar y aprobar el contenido mensual de Instagram |
| Contenido | 4 piezas al mes: **2 carruseles + 2 reels**, una por semana del mes siguiente |
| Secciones | **1) Propuestas del próximo mes**: comentarios por pieza, casilla "Aprobado" y botón "Aplicar ajustes". **2) Repositorio**: histórico de contenidos con sus fechas |
| Entregable final | **PowerPoint (.pptx)** con una slide por contenido: formato, tamaño oficial, caption, textos por tarjeta o escena, hashtags, fuente y fecha sugerida, sobre la plantilla de marca RC |
| Generación | Automática a partir del **día 15** de cada mes, más un botón "Generar ahora" |
| Hosting | **Vercel**: frontend estático y **una sola** función Python. **Supabase**: Postgres y login |
| LLM | API de Anthropic (Claude) con la herramienta de servidor `web_search` para investigar tendencias reales |
| Dependencias | Frontend: **ninguna** (HTML, CSS y JS nativos, sin build). Backend: **`anthropic` y `python-pptx`**. Supabase se consume por REST con la librería estándar |

---

## 1. Objetivo de negocio (léelo antes de programar)

RC Farias es una agencia BTL colombiana, miembro de Constellation, especializada en experiencias de marca para grandes empresas. La app existe para que **cada mes haya contenido educativo, diferenciado y basado en datos reales** para gerentes de marca y mercadeo, con:
- **control humano**: nada sale sin aprobación explícita, pieza por pieza;
- **ciclo de ajustes rápido**: comentar, pulsar un botón y recibir la versión corregida;
- **entrega lista para producción**: un PPT que el diseñador o editor usa directamente, con medidas correctas;
- **memoria**: un repositorio que evita repetir tendencias y deja trazabilidad.

Implicaciones de diseño:
1. **La veracidad importa más que la creatividad.** Cada pieza se apoya en una fuente real, con URL y fecha, que se puede verificar.
2. **No repetir es un requisito duro.** Se controla en el prompt (el modelo ve el historial) y en el código (una validación determinista de similitud).
3. **Las piezas son independientes.** Se generan, comentan, ajustan y aprueban una por una.

---

## 2. Principios de diseño (restricciones no negociables)

1. **Mínima dependencia de terceros**
   - Frontend: `index.html`, `app.js` y `estilos.css`, sin frameworks, sin npm, sin bundler y sin librerías de CDN.
   - Backend: Python 3.12 con la librería estándar (`http.server`, `urllib.request`, `json`, `re`, `unicodedata`, `datetime`, `string`, `io`, `unittest`), **más `anthropic` y `python-pptx`**, ambos con versión fijada.
   - Supabase se usa por **REST (PostgREST y Auth)** con `urllib`. No se usan `supabase-py`, `supabase-js` ni ORMs.
   - Nada de Next.js, React, Tailwind, LangChain, pydantic ni requests.
2. **Mínimo cómputo**
   - **Una llamada al LLM por pieza** (4 al mes) y **una por pieza ajustada**. El historial compacto pesa unos 2.000 tokens al año.
   - Lo determinista lo resuelve el código: rotación de pilares, validación de reglas, fechas y armado del PPT.
   - `web_search` va acotado: `max_uses` 3 al generar y 2 al ajustar.
   - **Sin prompt caching.** Con este volumen no aporta nada.
   - **Una sola función serverless** (`api/index.py`) que enruta todos los endpoints: un único bundle y menos arranques en frío.
3. **Cada operación larga cabe en una invocación**
   - Generar o ajustar **una** pieza por request. El frontend o el cron encadenan las 4, así se evita depender del límite de duración de la función.
4. **Idempotencia y trazabilidad**
   - Cada cambio de contenido crea una **versión** de la pieza, y cada comentario registra en qué versión quedó aplicado.
5. **Fallar de forma visible**
   - Si una pieza incumple reglas tras los reintentos, se muestra en la UI con `⚠️` y la lista de errores, y **no se puede aprobar** sin revisarla.

---

## 3. Arquitectura

```
                    ┌──────────────── Vercel ────────────────┐
 Navegador  ───────▶│  public/ (HTML+JS+CSS estáticos)       │
 (solo tú)          │                                        │
     │  fetch JSON  │  api/index.py  (1 función Python)      │──── HTTPS ───▶ API de Anthropic
     └─────────────▶│   ├─ /api/config                       │               (Claude + web_search)
                    │   ├─ /api/meses, /api/piezas …         │
                    │   ├─ /api/generar-pieza                │──── REST ────▶ Supabase
                    │   ├─ /api/ajustar-pieza                │               (Postgres + Auth)
                    │   ├─ /api/exportar-pptx                │
                    │   └─ /api/diario  ◀── Vercel Cron (1×/día)
                    └────────────────────────────────────────┘
```

- **Login:** el frontend se autentica contra Supabase Auth por REST (`/auth/v1/token`) y envía el `access_token` a la API en `Authorization: Bearer`.
- **Autorización en la API:** en cada request se valida el token con `GET {SUPABASE_URL}/auth/v1/user` y se comprueba que el email sea `OWNER_EMAIL`. Después la API opera sobre Postgres con la `service_role` key, que **solo vive en el servidor**.
- **Cron diario** (`/api/diario`, protegido con `CRON_SECRET`), con dos funciones:
  1. **Mantener activo Supabase.** Los proyectos gratuitos se pausan por inactividad; ver la sección 13.
  2. **Arrancar la generación.** Si en Bogotá es día ≥ 15 y no existe el mes siguiente, lo crea y genera piezas mientras le quede presupuesto de tiempo. Las piezas pendientes se completan en la siguiente ejecución o al abrir la app.

### 3.1 Estructura de archivos

```
.
├── PLAN.md
├── README.md                      ← setup: Supabase, Vercel, variables, primer usuario
├── vercel.json                    ← rewrites /api/* → api/index.py, maxDuration, cron
├── requirements.txt               ← anthropic==<fijada>, python-pptx==<fijada>
├── public/
│   ├── index.html                 ← login + 2 secciones (tabs)
│   ├── app.js                     ← estado, fetch, render (vanilla)
│   └── estilos.css
├── api/
│   └── index.py                   ← class handler(BaseHTTPRequestHandler) + router
├── rc/                            ← lógica compartida (importada por api/index.py)
│   ├── config.py                  ← variables de entorno + config/*.json
│   ├── db.py                      ← cliente PostgREST mínimo con urllib
│   ├── auth.py                    ← validación del token con Supabase Auth
│   ├── planificador.py            ← rotación determinista de pilares/tipos + fechas
│   ├── prompts.py
│   ├── esquema.py                 ← JSON Schema de una pieza
│   ├── generador.py               ← llamadas a Claude (generar / ajustar)
│   ├── validador.py               ← reglas deterministas
│   └── pptx_export.py             ← armado del PowerPoint
├── config/
│   ├── ajustes.json
│   ├── pilares.json
│   └── instagram_specs.json       ← tamaños oficiales (fecha de verificación incluida)
├── prompts/{sistema.md, generar.md, ajustar.md}
├── plantilla/
│   ├── logo_rc_rojo.png           ← logo sobre fondos claros (entregado por RC)
│   ├── logo_rc_azul.png           ← logo sobre fondos claros, versión sobria
│   ├── logo_rc_blanco.png         ← logo sobre fondos azules
│   ├── guia_visual_referencia.png ← guía visual completa (baja resolución, referencia)
│   └── paleta_color.png           ← paleta y gradientes oficiales (alta resolución)
│   (el diseño del PPT se construye por código desde config/marca.json; no hace falta un .pptx maestro)
├── config/marca.json              ← colores HEX y tipografías de la guía visual (sección 9.3)
├── supabase/migrations/001_esquema.sql
└── tests/                         ← unittest, sin red
    ├── fixtures/
    ├── test_validador.py
    ├── test_planificador.py
    └── test_pptx_export.py
```

> **Verificar en la Fase 1** que Vercel incluya la carpeta `rc/`, `config/`, `prompts/` y `plantilla/` en el bundle de `api/index.py`. Si no, usar `includeFiles` en `vercel.json`.

---

## 4. Modelo de datos (Supabase Postgres)

`supabase/migrations/001_esquema.sql`:

```sql
create type estado_mes   as enum ('generando','en_revision','aprobado','entregado','historico');
create type estado_pieza as enum ('pendiente','generando','generada','ajustando','aprobada','error');

create table meses (
  id            bigint generated always as identity primary key,
  mes_objetivo  date not null unique,            -- siempre día 1: 2026-10-01
  estado        estado_mes not null default 'generando',
  creado_en     timestamptz not null default now(),
  aprobado_en   timestamptz,
  entregado_en  timestamptz                      -- primera descarga del PPT
);

create table piezas (
  id              bigint generated always as identity primary key,
  mes_id          bigint not null references meses(id) on delete cascade,
  semana          smallint not null check (semana between 1 and 5),
  fecha_publicacion date not null,               -- sugerida al crear; editable por el usuario pieza a pieza
  formato         text not null check (formato in ('Carrusel','Reel')),
  tipo            text not null,
  pilar           text not null,
  estado          estado_pieza not null default 'pendiente',
  version         int not null default 0,        -- 0 = aún sin contenido
  contenido       jsonb,                         -- objeto del JSON Schema (sección 8.2)
  validacion      jsonb,                         -- {"errores":[], "advertencias":[]}
  uso_tokens      jsonb,                         -- usage acumulado (costo)
  error_msg       text,
  aprobada_en     timestamptz,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now(),
  unique (mes_id, semana)
);

create table versiones_pieza (                   -- auditoría: snapshot por versión
  id         bigint generated always as identity primary key,
  pieza_id   bigint not null references piezas(id) on delete cascade,
  version    int not null,
  contenido  jsonb not null,
  motivo     text not null,                      -- 'generacion' | 'ajuste'
  creado_en  timestamptz not null default now(),
  unique (pieza_id, version)
);

create table comentarios (
  id                  bigint generated always as identity primary key,
  pieza_id            bigint not null references piezas(id) on delete cascade,
  texto               text not null check (length(texto) between 1 and 2000),
  version_comentada   int not null,
  aplicado_en         timestamptz,               -- null = pendiente
  version_resultante  int,
  creado_en           timestamptz not null default now()
);

-- Seguridad: RLS activado y SIN políticas para anon/authenticated.
-- Solo la service_role (servidor) puede leer/escribir.
alter table meses            enable row level security;
alter table piezas           enable row level security;
alter table versiones_pieza  enable row level security;
alter table comentarios      enable row level security;
```

**Repositorio = consulta**, no una tabla aparte: todas las piezas de meses `aprobado`, `entregado` o `historico`, con sus fechas.

**Historial anti-repetición** (para prompt y validador): la tendencia y la estrategia de todas las piezas con `contenido` no nulo, de cualquier mes, **excepto** el mes en curso, al que se le pasa la lista de piezas hermanas por separado.

**Migración del historial previo:** importar el historial existente (de Make u otra fuente) como un mes con `estado = 'historico'` y piezas con `contenido` mínimo (`tema_especifico`, `tendencia` y `estrategia_clave`).

**Temas ya usados, confirmados por RC:** se cargan como semilla del histórico con solo `tema_especifico`, para que no se repitan:
1. Cómo llegar a las nuevas generaciones
2. Qué es el greenwashing en las marcas
3. Por qué necesitas datos de tus eventos
4. Impacto de la IA en el BTL
5. Cringe marketing
6. BTL phygital
7. Marketing sensorial

---

## 5. Flujos y estados

### 5.1 Estados de una pieza

```
pendiente ──generar──▶ generando ──ok──▶ generada ──(check Aprobado)──▶ aprobada
                          │                 │  ▲                           │
                          └──fallo──▶ error │  └──ok── ajustando ◀─────────┘ (desmarcar)
                                            └──(comentarios + botón)──▶ ajustando
```

Reglas:
- **Comentar:** se pueden agregar varios comentarios a una pieza en estado `generada`. Quedan pendientes hasta que se pulsa "Aplicar ajustes".
- **Casilla "Aprobado":**
  - Solo se puede marcar en estado `generada`, **sin comentarios pendientes** y **sin errores de validación**. Las advertencias sí se permiten.
  - Al desmarcarla, la pieza vuelve a `generada`.
- **Botón "Aplicar ajustes":** es **global** para el mes. Procesa en secuencia cada pieza que tenga comentarios pendientes, llamando a `/api/ajustar-pieza` una por una y mostrando el progreso. Queda deshabilitado si no hay comentarios pendientes.
- **Mes:**
  - Pasa a `en_revision` cuando las 4 piezas tienen contenido.
  - Pasa a `aprobado` cuando las 4 están `aprobada`, lo que habilita "Descargar PowerPoint".
  - La primera descarga fija `entregado_en` y el mes pasa a `entregado`.
- **Cambios después de aprobar:** si ya está `aprobado` o `entregado` y se desmarca una pieza, el mes vuelve a `en_revision`. El repositorio siempre muestra la última versión aprobada.

### 5.2 Generación mensual

1. El cron diario (o el botón "Generar ahora") llama a `iniciar_mes(mes_objetivo)`:
   - crea el registro del mes (idempotente gracias a `unique`);
   - calcula 4 slots con `planificador` y crea 4 piezas `pendiente`.
2. Luego llama `generar_pieza(id)` en secuencia mientras `tiempo_restante > 90 s`. Presupuesto total: `maxDuration − 30 s`.
3. Al abrir la app, si hay piezas `pendiente` o `error`, el frontend llama a `/api/generar-pieza` para cada una y muestra el progreso. En estado `error` también hay un botón "Reintentar" por pieza.
4. **Protección contra ejecución doble:** `generar_pieza` hace un update condicional `estado in ('pendiente','error') → 'generando'`. Si no afecta ninguna fila, sale sin hacer nada.
   - Si una pieza lleva más de 10 minutos en `generando` (una invocación que murió), se considera `error`.

**Mes objetivo:** el mes siguiente a la fecha actual en `America/Bogota`. Se puede sobrescribir con un selector en "Generar ahora".

### 5.3 Fechas de publicación (elegidas por el usuario, pieza a pieza)

- Al crear los slots, cada pieza recibe una fecha **propuesta**: el martes de su semana (N-ésimo martes del mes objetivo, según `ajustes.dia_publicacion_propuesto`). Es una función pura con tests.
- El usuario **cambia la fecha de cada post individualmente** con un selector de fecha en su tarjeta, en cualquier estado salvo `generando` o `ajustando`.
  - Cambiar la fecha **no** crea una versión nueva ni quita la aprobación, porque no altera el contenido.
- Advertencias no bloqueantes en la UI: si la fecha cae fuera del mes objetivo o si dos piezas tienen la misma fecha.
- La fecha elegida se usa en el Repositorio y en el PowerPoint.

---

## 6. Interfaz (frontend vanilla)

### 6.1 Login
- Email y contraseña contra `POST {SUPABASE_URL}/auth/v1/token?grant_type=password` (header `apikey: <anon key>`).
- Tokens guardados en `localStorage`, dentro de `try/catch`. Se renuevan con `grant_type=refresh_token` cuando la API responde 401.
- **Registro deshabilitado** en Supabase: el único usuario se crea a mano desde el panel.

### 6.2 Sección "Propuestas del próximo mes" (pestaña por defecto)

```
┌ Octubre · En revisión · 2/4 aprobadas ─ [Generar ahora] [Aplicar ajustes (3)] [Descargar PowerPoint] ┐
│                                                                                                      │
│ ┌ Semana 1 · Carrusel · Educativo · Publicar: [📅 06/10/2026] ──────── v2 ── ☐ Aprobado ┐              │
│ │ Pilar: Trade marketing…   Tema: …                                                    │              │
│ │ Investigación: tendencia · resumen · Fuente (enlace, fecha)                          │              │
│ │ Tarjetas: 1 Gancho … | 2 … | 3 … | 4 … | 5 Cierre …                                  │              │
│ │ Caption … (con CTA)            Hashtags: #RCFarias #… #…                             │              │
│ │ ⚠️ Advertencias / errores (si hay)                                                    │              │
│ │ Comentarios: • "Cambia el gancho…" (pendiente) • "…" (aplicado en v2)                │              │
│ │ [ Escribe un comentario…                                   ] [Agregar]              │              │
│ │ Ver versiones anteriores ▸                                                           │              │
│ └──────────────────────────────────────────────────────────────────────────────────────┘              │
│ … (4 tarjetas)                                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Los conteos de palabras se muestran junto a cada texto (p. ej. `7/8`) como ayuda visual.
- Mientras una pieza está `generando` o `ajustando`, su tarjeta muestra un indicador y bloquea los controles.

### 6.3 Sección "Repositorio"
- Tabla con columnas: mes objetivo, semana, **fecha de publicación**, formato, tipo, pilar, tema, tendencia, **fecha de creación**, **fecha de aprobación** y **fecha de entrega**.
- Filtros por mes, formato y pilar, aplicados en el cliente (el volumen es pequeño).
- Al hacer clic en una fila se abre el detalle completo en modo solo lectura, con sus versiones.
- Botón "Descargar PPT" por mes para re-descargarlo.

### 6.4 Requisitos de UI
- Responsive: usable en móvil con márgenes laterales de 16 px y sin scroll horizontal.
- Accesible: labels en los inputs, foco visible y contraste AA.
- Todo el texto de la UI en español.

---

## 7. API (`api/index.py`)

Todas las rutas, salvo `/api/config` y `/api/diario`, exigen un `Bearer` válido del dueño. Las respuestas son JSON, excepto el PPTX.

| Método y ruta | Acción |
|---|---|
| `GET /api/config` | `{supabase_url, supabase_anon_key}` para el login. Son valores públicos por diseño |
| `GET /api/mes-actual` | El mes objetivo con sus 4 piezas y los comentarios de cada una |
| `POST /api/iniciar-mes` `{mes?}` | Crea el mes y los slots (idempotente) |
| `POST /api/generar-pieza` `{pieza_id}` | Genera una pieza (sección 8) |
| `POST /api/comentarios` `{pieza_id, texto}` | Agrega un comentario |
| `DELETE /api/comentarios/{id}` | Borra un comentario **pendiente** |
| `POST /api/ajustar-pieza` `{pieza_id}` | Aplica todos los comentarios pendientes de la pieza (sección 8.4) |
| `POST /api/aprobar` `{pieza_id, aprobada: bool}` | Marca o desmarca la aprobación (valida las reglas de 5.1) |
| `POST /api/fecha` `{pieza_id, fecha: "AAAA-MM-DD"}` | Cambia la fecha de publicación de una pieza (5.3) |
| `GET /api/exportar-pptx?mes=AAAA-MM` | Devuelve el `.pptx` (`Content-Disposition: attachment`). Solo si el mes está `aprobado`, `entregado` o `historico` |
| `GET /api/repositorio` | Listado de piezas del repositorio |
| `GET /api/piezas/{id}/versiones` | Versiones de una pieza |
| `GET /api/diario` | Cron. Exige `Authorization: Bearer {CRON_SECRET}` |

`db.py`: un wrapper de unas 60 líneas sobre PostgREST (`GET/POST/PATCH/DELETE {SUPABASE_URL}/rest/v1/<tabla>?…` con los headers `apikey` y `Authorization: Bearer <service_role>`, y `Prefer: return=representation`). Los updates condicionales usan filtros de PostgREST (`?id=eq.5&estado=in.(pendiente,error)`).

---

## 8. Generación con Claude

### 8.1 Parámetros de la llamada (SDK Python oficial)

```python
client = anthropic.Anthropic()  # ANTHROPIC_API_KEY
with client.messages.stream(
    model=ajustes["modelo"],                 # "claude-opus-5"
    max_tokens=16000,
    system=sistema,
    messages=[{"role": "user", "content": usuario}],
    tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
    output_config={"effort": ajustes["effort"],   # "medium"
                   "format": {"type": "json_schema", "schema": ESQUEMA_PIEZA}},
) as stream:
    respuesta = stream.get_final_message()
```

Reglas obligatorias:
- **No** enviar `thinking` con `budget_tokens`, `temperature`/`top_p` ni prefill: dan error 400 en los modelos actuales. Con Opus 5, si se omite `thinking`, el modelo usa pensamiento adaptativo.
- **No** declarar `code_execution` junto a `web_search_20260209`, porque ese tipo ya incluye filtrado dinámico.
- Revisar `stop_reason` **antes** de leer el contenido:
  - `pause_turn`: reenviar agregando `{"role":"assistant","content": respuesta.content}`, sin añadir un mensaje de usuario. Máximo 3 veces.
  - `refusal`: marcar la pieza como `error` con su mensaje.
  - `max_tokens`: reintentar una vez con el doble de `max_tokens`.
- Leer el JSON del **último** bloque `text` con `json.loads`.
- Extraer todas las URLs de los bloques `web_search_tool_result`:
  - si `content` es una lista, cada resultado trae su `url`;
  - si `content` es un objeto con `error_code`, la búsqueda falló: registrarlo en el log.
- Guardar `respuesta.usage` en `piezas.uso_tokens` para medir el costo real.
- Errores del SDK, del más específico al más general: `RateLimitError` → `APIStatusError` → `APIConnectionError`. El SDK ya reintenta 2 veces los 429 y 5xx.
- El modelo se configura en `ajustes.json`: `claude-opus-5` por defecto, `claude-sonnet-5` como opción más barata. **Elegir entre ellos es una decisión de negocio de RC.**

> ⚠️ **Riesgo por verificar en la Fase 1:** la documentación indica que structured outputs es incompatible con las *citations* de documentos, y no está confirmado si ocurre lo mismo con las citas de `web_search`.
> - Hacer una llamada de prueba.
> - **Plan B** si devuelve 400: quitar `output_config.format`, pegar el esquema en el prompt ("responde solo con JSON que cumpla este esquema") y validar localmente. El resto del diseño no cambia.

### 8.2 JSON Schema de una pieza (`rc/esquema.py`)

```python
INVESTIGACION = {"type": "object", "properties": {
    "tendencia": {"type": "string"}, "resumen": {"type": "string"},
    "estrategia_clave": {"type": "string"}, "fuente_titulo": {"type": "string"},
    "fuente_url": {"type": "string"}, "fuente_fecha": {"type": "string"}},
  "required": ["tendencia","resumen","estrategia_clave","fuente_titulo","fuente_url","fuente_fecha"],
  "additionalProperties": False}

COMUNES = {"tema_especifico": {"type": "string"}, "investigacion": INVESTIGACION,
           "caption": {"type": "string"}, "cta": {"type": "string"},
           "hashtags": {"type": "array", "items": {"type": "string"}}}

CARRUSEL = {"type": "object", "properties": {**COMUNES,
    "formato": {"type": "string", "enum": ["Carrusel"]},
    "slide_1_gancho": {"type": "string"}, "slide_2": {"type": "string"},
    "slide_3": {"type": "string"}, "slide_4": {"type": "string"},
    "slide_5_cierre": {"type": "string"}},
  "required": [*COMUNES, "formato","slide_1_gancho","slide_2","slide_3","slide_4","slide_5_cierre"],
  "additionalProperties": False}

REEL = {"type": "object", "properties": {**COMUNES,
    "formato": {"type": "string", "enum": ["Reel"]},
    "escena_1_gancho": {"type": "string"},        # 0-5 s
    "escena_2_desarrollo_a": {"type": "string"},  # 5-12 s
    "escena_3_desarrollo_b": {"type": "string"},  # 12-20 s
    "escena_4_desarrollo_c": {"type": "string"},  # 20-25 s
    "escena_5_cta": {"type": "string"}},          # 25-30 s
  "required": [*COMUNES, "formato","escena_1_gancho","escena_2_desarrollo_a",
               "escena_3_desarrollo_b","escena_4_desarrollo_c","escena_5_cta"],
  "additionalProperties": False}

# Se usa el esquema del formato del slot (no anyOf): más simple y el modelo no puede equivocar formato.
ESQUEMA_PIEZA = {"Carrusel": CARRUSEL, "Reel": REEL}
```

### 8.3 Prompts

**`prompts/sistema.md`**

```
Eres el estratega de contenido de RC Farias, agencia BTL colombiana miembro de Constellation,
especializada en experiencias de marca memorables para grandes empresas.

AUDIENCIA: gerentes de marca y mercadeo de empresas medianas y grandes.
TONO: educativo, profesional y directo.
VOZ: habla desde RC Farias en primera persona plural: creamos / ejecutamos / diseñamos.

REGLAS DURAS (se validan automáticamente; si no se cumplen, la pieza se rechaza):
- Nunca uses años específicos (p. ej. 2025, 2026) en tarjetas, escenas ni caption. Deben ser atemporales.
- Prohibidos los hashtags #viral #explore #trending #fyp y cualquier hashtag genérico de relleno.
- El caption debe terminar EXACTAMENTE con: 📲 Síguenos para más ideas que conectan data, experiencia y negocio.
  Ese texto también va en el campo "cta".
- Nunca repitas tendencias ni estrategias del HISTORIAL ni de las OTRAS PIEZAS DEL MES.

TEMÁTICA: toda pieza trata sobre TENDENCIAS DE MARKETING ESTRATÉGICO y/o TENDENCIAS DE MARKETING BTL.
Referencia de la granularidad y el estilo de tema esperado (YA USADOS: no repetirlos, solo tomar el estilo):
"Cómo llegar a las nuevas generaciones", "Qué es el greenwashing en las marcas",
"Por qué necesitas datos de tus eventos", "Impacto de la IA en el BTL", "Cringe marketing",
"BTL phygital", "Marketing sensorial".
Es decir: un concepto, fenómeno o pregunta concreta que un gerente de marca reconozca y quiera entender.

INVESTIGACIÓN (obligatoria):
- Usa la herramienta de búsqueda web. No respondas de memoria.
- Identifica 1 tendencia o estrategia ACTUAL y REAL sobre el pilar indicado.
- Resúmela en 2-3 líneas con datos verificables (cifra, estudio o caso concreto).
- Reporta la fuente exacta: título, URL y fecha de publicación (o "sin fecha visible").
- Prefiere fuentes primarias o de industria reconocidas y publicadas en los últimos 18 meses.
- Si no hay evidencia sólida, elige otra tendencia. Nunca inventes datos ni URLs.

FORMATO CARRUSEL:
- slide_1_gancho: máximo 8 palabras. Afirmación provocadora o pregunta disruptiva.
- slide_2, slide_3, slide_4: máximo 30 palabras cada uno.
- slide_5_cierre: máximo 30 palabras. Debe mencionar "RC Farias" y "Constellation".
- hashtags: exactamente 3, en este orden: #RCFarias, 1 de nicho de servicio real
  (BTL, activaciones, eventos, estrategia) y 1 de comunidad/industria (marketing, marcas, trade).

FORMATO REEL (guion de 30 segundos; cada campo es el TEXTO EN PANTALLA):
- escena_1_gancho (0-5 s): máximo 6 palabras, afirmación provocadora.
- escena_2_desarrollo_a (5-12 s), escena_3_desarrollo_b (12-20 s), escena_4_desarrollo_c (20-25 s):
  máximo 8 palabras cada una.
- escena_5_cta (25-30 s): máximo 6 palabras, llamada a la acción directa.
- hashtags: entre 3 y 5, el primero siempre #RCFarias.

CAPTION: atemporal, sin años, máximo 150 palabras, cierra con el CTA obligatorio.

Responde únicamente con el JSON del esquema indicado.
```

**`prompts/generar.md`**

```
HISTORIAL DE CONTENIDO PUBLICADO (no repetir estas tendencias ni estrategias):
$historial

OTRAS PIEZAS DE ESTE MES (tampoco repetir):
$hermanas

Genera UNA pieza de Instagram:
Semana: $semana
Formato: $formato
Tipo: $tipo
Pilar: $pilar

Propón un "tema_especifico" dentro del pilar, investiga con búsqueda web y redacta el contenido.
```

**`prompts/ajustar.md`** (con `web_search` limitado a `max_uses: 2` y `effort: "low"`)

```
Esta es la versión actual de una pieza y los comentarios del responsable de contenido.
Aplica TODOS los comentarios. Conserva lo que no se pide cambiar.
Si un comentario pide cambiar la tendencia o un dato, investiga de nuevo con búsqueda web
y actualiza la investigación y la fuente; si no, no uses la búsqueda.
Todas las reglas duras siguen vigentes.

COMENTARIOS:
$comentarios

HISTORIAL (no repetir):
$historial

OTRAS PIEZAS DEL MES:
$hermanas

PIEZA ACTUAL (JSON):
$pieza_json
```

`$historial` son líneas `- AAAA-MM | pilar | tendencia | estrategia_clave`; `$hermanas` tiene el mismo formato. Los comentarios los escribe el único usuario autenticado, así que se consideran instrucciones de confianza.

### 8.4 Flujo de `generar_pieza` y `ajustar_pieza`

1. Hacer el update condicional de estado a `generando` o `ajustando`.
2. Armar el prompt y llamar a Claude.
3. Validar (sección 8.5).
4. Si hay errores **reparables** (V2 a V8), hacer hasta 2 llamadas de reparación **sin** `tools` y con `effort: "low"`, enviando la pieza y la lista de errores.
5. Guardar:
   - `contenido`, `validacion`, `version + 1` y la fila en `versiones_pieza`;
   - estado `generada`, aunque queden errores (la UI los muestra y bloquea la aprobación);
   - si hubo ajuste, los comentarios pendientes pasan a `aplicado_en = now()` y `version_resultante`.
6. Si ocurre una excepción, estado `error` con `error_msg`. Nunca debe dejar la pieza en `generando`.

### 8.5 Validador determinista (`rc/validador.py`)

**Palabra:** token separado por espacios que contiene al menos un carácter `\w`. Los emojis sueltos no cuentan.

| # | Regla | Aplica a | Severidad |
|---|---|---|---|
| V1 | Formato de la respuesta igual al del slot | Ambos | Error |
| V2 | Slide 1 ≤ 8 palabras; slides 2-5 ≤ 30 | Carrusel | Error |
| V3 | Slide 5 contiene "RC Farias" y "Constellation" (sin distinguir mayúsculas) | Carrusel | Error |
| V4 | Escenas 1 y 5 ≤ 6 palabras; escenas 2-4 ≤ 8 | Reel | Error |
| V5 | Ningún año `\b(19\|20)\d{2}\b` en tarjetas, escenas ni caption | Ambos | Error |
| V6 | `cta` igual al texto exacto y el caption termina con él (tras `strip()`) | Ambos | Error |
| V7 | Hashtags: carrusel exactamente 3; reel entre 3 y 5; el primero es `#RCFarias`; sin duplicados; `^#\w+$` | Ambos | Error |
| V8 | Sin hashtags de la lista negra (`#viral #explore #trending #fyp #instagood #love #follow #like4like`, ampliable; comparación sin mayúsculas ni tildes). Caption ≤ 150 palabras | Ambos | Error |
| V9 | `fuente_url` es `https://` y está entre las URLs devueltas por `web_search` **en esta pieza** (comparación sin query string ni barra final). En un ajuste sin búsqueda nueva vale la URL ya validada en la versión anterior | Ambos | Error, no reparable |
| V10 | Jaccard < 0,5 contra el historial y contra las hermanas (sección 8.6) | Ambos | Error, no reparable. La UI sugiere comentar "cambia la tendencia" |
| V11 | `fuente_fecha` interpretable y ≤ 18 meses, o `"sin fecha visible"` | Ambos | Advertencia |
| V12 | `resumen` contiene al menos un número | Ambos | Advertencia |

### 8.6 Similitud anti-repetición (sin embeddings)

1. Texto = `tema_especifico + " " + tendencia + " " + estrategia_clave`. En los temas semilla del histórico solo hay `tema_especifico`: contra ellos se compara únicamente `tema_especifico`, con umbral 0,6, porque los textos son cortos.
2. Normalizar:
   - pasar a minúsculas;
   - quitar tildes con `unicodedata.normalize("NFKD")`;
   - quitar puntuación;
   - quitar stopwords españolas (lista embebida de unas 60 palabras).
3. Calcular la similitud de Jaccard entre los conjuntos de palabras.
4. Si es ≥ `umbral_similitud` (0,5, configurable), la pieza es un duplicado.
5. Calibrar el umbral con datos reales en la Fase 3.

---

## 9. Exportación a PowerPoint (`rc/pptx_export.py`)

### 9.1 Tamaños de Instagram (`config/instagram_specs.json`)

Verificado el **25/09/2026** en fuentes secundarias actualizadas (sección 16). Instagram no publica una tabla oficial única de medidas. Revisar este archivo cada 6 meses: **los valores viven en config, no en código.**

```json
{
  "verificado": "2026-09-25",
  "Carrusel": {
    "tamano_px": "1080 × 1350",
    "relacion": "4:5",
    "notas": "Todas las tarjetas con la misma relación de aspecto. En la grilla del perfil (3:4) se recorta un poco arriba y abajo: mantener lo clave de la tarjeta 1 en el centro."
  },
  "Reel": {
    "tamano_px": "1080 × 1920",
    "relacion": "9:16",
    "portada": "1080 × 1920; en la grilla del perfil se ve el recorte central 3:4 (1080 × 1440)",
    "zona_segura": "Evitar texto en los ~220 px superiores y ~450 px inferiores (interfaz de Instagram)",
    "video": "MP4/MOV, H.264, 30 fps"
  }
}
```

> **Decisión de RC:** carrusel en **4:5 (1080 × 1350)**. Si en el futuro se quiere 3:4 (1080 × 1440, admitido desde mayo de 2025), basta con editar este JSON.

### 9.2 Estructura del archivo

- Presentación **16:9** construida por código con `python-pptx`, usando los colores, tipografías y logos de la sección 9.3. No se necesita un `.pptx` maestro.
- **Slide 0, portada:** fondo Azul RC, logo blanco, "Contenido Instagram · <Mes AAAA>" en Arial Black blanco, la fecha de aprobación y el resumen de las 4 piezas con su fecha de publicación. La portada sí puede llevar el año, porque es un documento interno.
- **Slides 1 a 4, una por contenido**, ordenadas por semana:

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ SEMANA 2 · REEL · Publicación: martes 13 oct                       [logo RC]  │
│ Tema: <tema_especifico>                                                        │
├──────────────────────────────┬────────────────────────────────────────────────┤
│ FICHA TÉCNICA                │ TEXTOS POR ESCENA  (Carrusel: POR TARJETA)     │
│ Formato: Reel                │ ┌────┬──────────┬───────────────────────────┐ │
│ Tamaño: 1080 × 1920 px (9:16)│ │ #  │ Tiempo   │ Texto en pantalla         │ │
│ Portada: …                   │ │ 1  │ 0-5 s    │ …                         │ │
│ Zona segura: …               │ │ 2  │ 5-12 s   │ …                         │ │
│ Tipo · Pilar                 │ │ …  │ …        │ …                         │ │
│                              │ └────┴──────────┴───────────────────────────┘ │
│ HASHTAGS                     │ (Carrusel: columnas # · Rol · Texto,           │
│ #RCFarias #… #…              │  rol = Gancho / Contenido / Cierre)            │
│                              │                                                │
│ FUENTE                       │ CAPTION                                        │
│ Tendencia · resumen          │ <párrafo del caption, incluido el CTA>         │
│ <título> — <url> (fecha)     │                                                │
└──────────────────────────────┴────────────────────────────────────────────────┘
```

- Tipografía: títulos de 20-24 pt; tabla, caption y ficha de 11-12 pt. Los límites de palabras de V2, V4 y V8 garantizan que el texto quepa. Aun así, `pptx_export` verifica que ningún texto exceda su caja (estimando líneas por caracteres) y, si hace falta, reduce la fuente hasta un mínimo de 9 pt.
- **Notas del orador** de cada slide: el `resumen` de la investigación completo, para el presentador.
- Nombre del archivo: `RC_Farias_Instagram_AAAA-MM.pptx`. Se genera en memoria (`io.BytesIO`) y **no se almacena**; se regenera en cada descarga desde los datos aprobados.
- Test: generar el PPTX desde fixtures, reabrirlo con `python-pptx` y comprobar 5 slides, los textos presentes y las medidas correctas por formato.

### 9.3 Identidad de marca (`config/marca.json`)

Paleta **confirmada por RC** a partir de la guía visual en alta resolución (25/09/2026). Los dos colores de logo se midieron en los archivos PNG entregados y se usan **solo** a través de las imágenes del logo, nunca como colores de interfaz.

```json
{
  "paleta": {
    "coral":      "#F65155",
    "celeste":    "#A9DAF1",
    "azul_medio": "#0069D1",
    "gris_claro": "#D8D6D2",
    "azul_marino":"#1F3864",
    "blanco":     "#FFFFFF"
  },
  "gradientes_verticales": {
    "cielo":  ["#FFFFFF", "#A9DAF1"],
    "azul":   ["#A9DAF1", "#0069D1"],
    "noche":  ["#0069D1", "#1F3864"],
    "coral":  ["#F65155", "#E88080"],
    "niebla": ["#D8D6D2", "#FFFFFF"]
  },
  "colores_logo_solo_referencia": {"rojo_logo": "#FE171F", "azul_logo": "#010E30"},
  "tipografias": {
    "titulos":    "Arial Black",
    "subtitulos": "Arial Bold",
    "parrafo":    "Arial",
    "secundaria": "Montserrat",
    "respaldo":   "Helvetica"
  },
  "logos": {
    "fondo_claro":        "plantilla/logo_rc_rojo.png",
    "fondo_claro_sobrio": "plantilla/logo_rc_azul.png",
    "fondo_oscuro":       "plantilla/logo_rc_blanco.png"
  }
}
```

- **Gradientes:** reproducen los cinco "fondos gradientes" de la guía, de arriba hacia abajo. Todos los extremos son colores de la paleta, salvo el final del gradiente `coral` (`#E88080`), que es una **aproximación** medida en la imagen: la guía no publica ese valor.
- **En el PPT:**
  - Arial en todo el documento. Viene instalada en Windows y macOS, así que no hace falta incrustar fuentes y la presentación se ve igual en cualquier equipo. Montserrat es la fuente secundaria de la guía, pero no se usa en el PPT porque podría no estar instalada.
  - **Portada:** fondo con el gradiente `noche`, logo blanco y título en Arial Black blanco.
  - **Slides de contenido:**
    - fondo blanco;
    - barra de título en `azul_marino` con texto blanco;
    - etiquetas de sección (FICHA TÉCNICA, CAPTION…) en Arial Bold `coral`;
    - encabezado de las tablas en `azul_marino` y filas alternas en `celeste` al 35 %;
    - enlaces de fuente en `azul_medio`;
    - logo rojo arriba a la derecha.
  - **Identificador de formato:** una etiqueta de color junto al título, `coral` para Reel y `azul_medio` para Carrusel, para distinguirlos de un vistazo.
  - Gradientes con `fill.gradient()` de `python-pptx` (ángulo de 90°).
- **En la web app:**
  - Los mismos tokens como variables CSS. Arial como fuente del sistema; no se carga Montserrat de Google Fonts, para no sumar dependencias externas.
  - Encabezado con el gradiente `noche` y el logo blanco.
  - Botón primario `azul_medio` con texto blanco (contraste 5,33:1, cumple AA). El coral no alcanza AA con ningún color de texto (3,44:1 con azul marino y 3,37:1 con blanco), así que se usa solo en acentos, bordes y texto grande.
  - Estados: aprobado en `azul_medio`, advertencia en `coral`.

---

## 10. Configuración

### 10.1 `config/ajustes.json`

```json
{
  "modelo": "claude-opus-5",
  "effort": "medium",
  "web_search_max_uses_generar": 3,
  "web_search_max_uses_ajustar": 2,
  "max_reparaciones": 2,
  "zona_horaria": "America/Bogota",
  "dia_inicio_generacion": 15,
  "dia_publicacion_propuesto": "martes",
  "umbral_similitud": 0.5,
  "antiguedad_max_fuente_meses": 18,
  "max_palabras_caption": 150,
  "calendario": [
    {"semana": 1, "formato": "Carrusel", "pilar": "Tendencias de marketing estratégico"},
    {"semana": 2, "formato": "Reel",     "pilar": "Tendencias de marketing BTL"},
    {"semana": 3, "formato": "Carrusel", "pilar": "Tendencias de marketing BTL"},
    {"semana": 4, "formato": "Reel",     "pilar": "Tendencias de marketing estratégico"}
  ]
}
```

### 10.2 `config/pilares.json` (confirmado por RC)

```json
{
  "pilares": [
    "Tendencias de marketing estratégico",
    "Tendencias de marketing BTL"
  ],
  "temas_ya_usados": [
    "Cómo llegar a las nuevas generaciones",
    "Qué es el greenwashing en las marcas",
    "Por qué necesitas datos de tus eventos",
    "Impacto de la IA en el BTL",
    "Cringe marketing",
    "BTL phygital",
    "Marketing sensorial"
  ],
  "tipos": ["Educativo", "Tendencia", "Mito vs. realidad", "Checklist / cómo hacerlo"]
}
```

**Asignación** (`planificador.py`, función pura con tests):
- **Pilar:** fijo por calendario. Cada mes lleva 2 piezas por pilar, y cada pilar tiene un carrusel y un reel. Un tema puede ser estratégico **y** BTL a la vez, porque RC los definió como "y/o".
- **Tipo:** rotación. Se elige el de uso más antiguo; los nunca usados van primero y, en empate, gana el orden de la lista. No se repite tipo entre dos piezas del mismo formato en el mes.
- `temas_ya_usados` alimenta el prompt (como referencia de estilo) y la semilla del histórico (4, sección 8.6).

> Tipos de contenido y reparto de pilares **confirmados por RC**.

### 10.3 Variables de entorno (Vercel → Settings → Environment Variables)

| Variable | Uso | ¿Secreta? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | Sí |
| `SUPABASE_URL` | REST y Auth | No |
| `SUPABASE_ANON_KEY` | Login desde el frontend | No (pública por diseño) |
| `SUPABASE_SERVICE_ROLE_KEY` | Acceso a la BD desde el servidor | **Sí, nunca va al frontend** |
| `OWNER_EMAIL` | Único usuario autorizado | No |
| `CRON_SECRET` | Protege `/api/diario` | Sí |

### 10.4 `vercel.json`

```json
{
  "rewrites": [{ "source": "/api/(.*)", "destination": "/api/index.py" }],
  "functions": { "api/index.py": { "maxDuration": 300 } },
  "crons": [{ "path": "/api/diario", "schedule": "17 12 * * *" }]
}
```

- El cron corre a las 12:17 UTC, que son las 07:17 en Bogotá.
- `maxDuration: 300` es el valor objetivo. **Verificar el máximo permitido por el plan contratado** y ajustarlo. El diseño (una pieza por request) funciona incluso con 60 s si cada pieza termina en ese tiempo; medirlo en la Fase 3.

---

## 11. Seguridad

1. La `service_role` key solo existe en el servidor. El frontend nunca la recibe.
2. RLS activado **sin políticas**: aunque alguien obtenga la anon key, no puede leer ni escribir tablas.
3. Registro de usuarios deshabilitado en Supabase Auth. Cada request valida el token **y** que el email sea `OWNER_EMAIL`.
4. `/api/diario` rechaza cualquier request sin `Authorization: Bearer {CRON_SECRET}`.
5. El frontend inserta el contenido generado con `textContent`, nunca con `innerHTML`. El contenido viene de la web a través del LLM y debe tratarse como no confiable.
6. Solo se muestran como enlace las URLs de fuente que empiecen por `https://` (`rel="noopener noreferrer"`).
7. Ningún secreto en logs, en el repo ni en respuestas de la API.

---

## 12. Plan de trabajo por fases

Cada fase se cierra con su criterio cumplido **antes** de pasar a la siguiente.

### Fase 1: Infraestructura y pruebas de riesgo (bloqueante)
- [ ] Proyecto Supabase: aplicar `001_esquema.sql`, deshabilitar el registro y crear el usuario dueño.
- [ ] Proyecto Vercel conectado al repo, con variables de entorno y `api/index.py` respondiendo a `GET /api/config`.
- [ ] Verificar que `rc/`, `config/`, `prompts/` y `plantilla/` entran en el bundle.
- [ ] Verificar el `maxDuration` real del plan.
- [ ] Prueba de API: una pieza con `web_search_20260209` + `output_config.format`. Documentar si funciona o si aplica el Plan B.
- ✅ Criterio: login funcionando, la API lee de Supabase y la prueba de Claude devuelve JSON parseable con las URLs extraídas.

### Fase 2: Lógica determinista (sin red)
- [ ] `planificador` (rotación y fechas), `validador` (V1 a V12 y similitud) y `pptx_export`, con tests `unittest`.
- ✅ Criterio: `python -m unittest discover -s tests` en verde y sin red.

### Fase 3: Generación y ajustes de punta a punta
- [ ] `generador` (generar, ajustar y reparar, con `pause_turn`, `refusal` y `max_tokens`) y los endpoints correspondientes.
- [ ] Generar un mes real. Revisar la calidad, abrir las URLs para comprobar que dicen lo que el resumen afirma, y revisar el costo en `uso_tokens` y la duración de cada request.
- [ ] Calibrar `umbral_similitud` y `effort`.
- ✅ Criterio: 4 piezas válidas, cada una generada en menos que `maxDuration`, con fuentes reales.

### Fase 4: Interfaz
- [ ] Login, Propuestas (comentarios, aprobación, aplicar ajustes, progreso, versiones) y Repositorio (tabla, filtros, detalle).
- ✅ Criterio: el flujo completo funciona desde el navegador de escritorio y del móvil, incluido comentar, ajustar y aprobar.

### Fase 5: PowerPoint y cron
- [ ] Exportación con la identidad de marca de 9.3. El cron diario inicia el mes el día 15 y mantiene activo Supabase.
- ✅ Criterio: el PPT abre sin errores en PowerPoint y Keynote, cada contenido ocupa su propia slide con las medidas correctas y el texto cabe. El cron, disparado a mano con `vercel crons run /api/diario`, crea el mes.

### Fase 6: Migración del historial
- [ ] Importar el historial previo como mes `historico`.
- ✅ Criterio: aparece en el Repositorio y lo usan el planificador y V10.

---

## 13. Costos y riesgos de plataforma (estimación; verificar antes de producción)

| Concepto | Estimación mensual |
|---|---|
| Claude, 4 generaciones (~15 mil tokens de entrada y ~3 mil de salida cada una, con `claude-opus-5` a USD 5 y 25 por millón) | ~USD 0,6 |
| Búsquedas web (≤ 12 generando y ≤ 8 ajustando, a USD 10 por 1.000) | ≤ USD 0,2 |
| Ajustes (~4 al mes, sin búsqueda en la mayoría) | ~USD 0,2 |
| **Subtotal Claude** | **≈ USD 1 al mes** |
| Vercel | Ver el riesgo 1 |
| Supabase | Plan gratuito (ver el riesgo 2) |

Riesgos que conviene conocer (datos de conocimiento general **no verificados en esta sesión**; confirmar en los términos vigentes):
1. **Vercel Hobby está pensado para uso personal y no comercial.** Una herramienta interna de una agencia probablemente requiera el plan **Pro** (del orden de USD 20 al mes). Revisar los términos antes de salir a producción.
2. **Supabase gratuito pausa los proyectos inactivos** (alrededor de una semana sin actividad). El cron diario hace una consulta mínima para mantenerlo activo. Si igual se pausa, el plan Pro de Supabase lo evita.
3. **Los cron de Vercel en Hobby** tienen límites de frecuencia y de precisión horaria. Una ejecución diaria es suficiente para este diseño.

Los precios de Claude salen de la documentación de Anthropic (caché del 24/06/2026) y los volúmenes de tokens son supuestos. **Medir el costo real en la Fase 3.**

---

## 14. Decisiones confirmadas y supuestos pendientes

**Confirmado por RC (25/09/2026):**
- Carrusel en **4:5 (1080 × 1350)**.
- **Fecha de publicación elegida por el usuario para cada post**, con una propuesta inicial.
- Pilares: **Tendencias de marketing estratégico y/o BTL**, más los 7 temas ya usados.
- Caption de máximo **150 palabras**.
- Marca: logos, paleta y tipografías entregados (9.3).

**Confirmado también (25/09/2026):** la paleta de color (9.3), los tipos de contenido y el reparto de pilares por semana.

**Confirmado también:** el día 15 se genera el contenido del mes siguiente; el botón "Aplicar ajustes" procesa todas las piezas con comentarios; la app no publica en Instagram, porque lo hace el equipo de publicación (Luis Alfonso) a partir del PowerPoint.

---

## 15. Mejoras recomendadas (fuera del alcance mínimo, ordenadas por impacto)

1. **Casos propios de RC.** Un archivo `config/casos_rc.md` con 5-10 casos reales, para que el cierre de cada pieza cite experiencia propia y no solo tendencias de la industria. Es lo que convierte a un gerente de marca en cliente.
2. **Métricas por pieza en el Repositorio.** Campos como alcance, guardados y compartidos, llenados a mano después de publicar. El planificador puede priorizar los pilares que mejor rinden.
3. **Brief visual por tarjeta o escena.** Un campo `nota_visual` (qué mostrar y qué B-roll usar) que llega al PPT y ahorra una ronda con el diseñador. Cuesta unos pocos cientos de tokens más.
4. **Botón "Regenerar desde cero"** por pieza, para cuando el comentario es "no me gusta nada".
5. **Exportar también en PDF**, para compartir con clientes sin PowerPoint.

---

## 16. Fuentes consultadas

**Medidas de Instagram** (consultadas el 25/09/2026; son fuentes secundarias porque Instagram no publica una tabla oficial única):
- [Instagram 3:4 Aspect Ratio: How to Post Photos Without Cropping (iTechGuides)](https://www.itechguides.com/instagram-rolls-out-support-for-standard-34-aspect-ratio-format-post-photos-without-cropping/). Cita el anuncio de Adam Mosseri en Threads del 28/05/2025 sobre el soporte de 3:4 en fotos y carruseles. Fecha del artículo no verificada.
- [Instagram Carousel Size 2026: 1080x1350px + Free Templates (Contentdrips)](https://contentdrips.com/blog/2026/05/instagram-carousel-size-format/), mayo de 2026.
- [Instagram Post Size 2026: 1080 x 1440 and Every Ratio (DreamPixelForge)](https://www.dreampixelforge.com/blog/instagram-post-size), 2026, sin fecha exacta visible.
- [Instagram Image Sizes in 2026 (Influencer Marketing Hub)](https://influencermarketinghub.com/instagram-image-sizes/), 2026.
- [Instagram Reels Size: 1080×1920 [Updated September 2026] (PostFast)](https://postfa.st/sizes/instagram/reels), septiembre de 2026.
- [Instagram Reel Size Guide 2026: Dimensions, Cover, Ratio & Safe Zone (Somake AI)](https://www.somake.ai/blog/instagram-reel-size-guide), 2026. Las zonas seguras que reporta provienen de la guía de anuncios de Meta.
- [Social media image sizes for all networks [September 2026] (Hootsuite)](https://blog.hootsuite.com/social-media-image-sizes-guide/), septiembre de 2026.

**Otras fuentes:**
- **API de Anthropic:** documentación incluida en la skill `claude-api` de Claude Code (caché del 24/06/2026). Cubre IDs y precios de modelos, `web_search_20260209`, structured outputs y sus incompatibilidades, `pause_turn`, `refusal`, `effort` y el precio de la búsqueda web.
- **Vercel:** documentación oficial consultada vía el conector de Vercel (25/09/2026). Cubre `maxDuration` en `vercel.json`, funciones Python y la configuración de `crons`. **No se pudo verificar** el máximo de duración ni los límites de cron por plan.
- **Supabase y términos de Vercel:** conocimiento general, **no verificado en esta sesión**.
