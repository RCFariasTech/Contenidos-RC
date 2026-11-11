# Contenido Instagram RC Farias

Web app privada para generar, revisar, ajustar y aprobar el contenido mensual de Instagram de RC Farias, y exportarlo a PowerPoint. El diseño completo está en [`PLAN.md`](PLAN.md).

## Estado (01/10/2026)

| Fase | Estado |
|---|---|
| 1. Infraestructura y prueba de API | ✅ Supabase, Vercel y Claude con búsqueda web funcionando |
| 2. Lógica determinista | ✅ Planificador y validador con tests |
| 3. Generación y ajustes | ✅ Primer mes real generado (≈ USD 1,49 con 3 ajustes) |
| 4. Interfaz | ✅ Propuestas (comentarios, ajustes, aprobación, fechas) y Repositorio |
| 5. PowerPoint y cron | ✅ Exportación con marca; cron diario desde el día 15 |
| 6. Migración del historial | ✅ 7 temas previos cargados como histórico |
| 7. Tarjetas de carrusel | ✅ PDF 4:5 (1080 × 1350) por carrusel con el sistema gráfico 2026: texto editable, 5 plantillas fijas, ícono isométrico y foto de Krea (`rc/tarjetas.py`) |

## Infraestructura

| Pieza | Dónde |
|---|---|
| Base de datos y login | Supabase, proyecto `contenidos-rc` (ref `xfcmsisssfgezvlxwqfj`, región `us-east-1`) |
| Frontend y API | Vercel, proyecto `contenidos-rc` → https://contenidos-rc.vercel.app (vinculado al repo: cada push a la rama de producción despliega) |
| LLM | API de Anthropic (Claude) con búsqueda web |

## Variables de entorno (Vercel → Settings → Environment Variables)

| Variable | Valor | Quién la configura |
|---|---|---|
| `SUPABASE_URL` | `https://xfcmsisssfgezvlxwqfj.supabase.co` | Ya configurada |
| `SUPABASE_ANON_KEY` | clave `anon` (pública) | Ya configurada |
| `OWNER_EMAIL` | `reini@rcfarias.com` | Ya configurada |
| `CRON_SECRET` | secreto aleatorio (tipo Sensitive) | Ya configurada |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API Keys → `service_role` (o una clave `sb_secret_…`). Tipo **Sensitive** | Dueño del proyecto |
| `ANTHROPIC_API_KEY2` (o `ANTHROPIC_API_KEY`) | console.anthropic.com → API Keys. Tipo **Sensitive**. Si existen las dos, se usa `ANTHROPIC_API_KEY2` | Dueño del proyecto |

### Envío del PowerPoint por correo (opcional)

El botón "Enviar por correo" usa SMTP con la librería estándar de Python (sin servicios de terceros). Para activarlo agrega en Vercel:

| Variable | Valor |
|---|---|
| `SMTP_USER` | Cuenta que envía, p. ej. `contenido.rcfarias@gmail.com` |
| `SMTP_PASSWORD` | **Contraseña de aplicación** de esa cuenta (no la contraseña normal). Tipo **Sensitive** |
| `SMTP_HOST` | Opcional. Por defecto `smtp.gmail.com` |
| `SMTP_PORT` | Opcional. Por defecto `587` (STARTTLS) |
| `SMTP_FROM` | Opcional. Por defecto igual a `SMTP_USER` |

En Gmail, la contraseña de aplicación se crea en la cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones (los nombres de los menús de Google pueden cambiar).
Mientras falten `SMTP_USER` y `SMTP_PASSWORD`, la app avisa que el envío no está activado y el resto funciona igual.

### Aviso a Microsoft Teams (opcional)

Cuando las 4 propuestas del mes quedan generadas (el cron desde el día 15 o el botón manual), la app publica un mensaje en un canal de Teams con un botón para abrir la app. Se avisa una sola vez por mes; un fallo de Teams nunca interrumpe la generación.

Teams ya no permite crear conectores de webhook entrantes nuevos; se usa un flujo de **Workflows** (Power Automate):
1. En el canal de Teams → ⋯ → **Workflows** → plantilla **Publicar en un canal cuando se reciba una solicitud de webhook** (disparador «Cuando se recibe una solicitud de webhook de Teams»; los nombres de los menús pueden cambiar).
2. Elige el equipo y el canal y crea el flujo; copia la **URL del webhook** que muestra.
3. En Vercel agrega `TEAMS_WEBHOOK_URL` con esa URL (tipo **Sensitive**) y, opcional, `APP_URL` (por defecto `https://contenidos-rc.vercel.app`). Vuelve a desplegar.
4. En la app → Configuración → **Enviar mensaje de prueba**.

El mensaje es una Adaptive Card dentro de `{"type": "message", "attachments": [...]}`, el formato que espera ese disparador.

### Ilustraciones 3D con Krea (opcional)

Sistema gráfico 2026 (guía visual de noviembre de 2026): paleta `paleta_2026` de `config/marca.json`, títulos en Space Grotesk y párrafos en Sora (`plantilla/fuentes/`), logo RC / FARÍAS blanco (`plantilla/logo_rc_blanco_2026.png`) e íconos de línea de la guía como vectores (`plantilla/iconos_linea/`, uno por concepto). Ya no se usan personajes ilustrados.

En las tarjetas 1, 2 y 3 de cada carrusel, los botones **Ícono de la tarjeta 1**, **Foto de la tarjeta 2** e **Ícono de la tarjeta 3** generan 2 variantes por clic con **Nano Banana Pro** en Krea (`config/ajustes.json` → `krea`). Los prompts de estilo están en `rc/estilo_iconos.py`:
- **Ícono (tarjeta 1):** ícono isométrico con el estilo de la guía, sobre azul marino; se envían como referencia los íconos isométricos de la guía publicados en `public/marca/iso/` (por eso `krea.url_publica` o `APP_URL` debe apuntar a la URL pública de la app).
- **Foto (tarjeta 2):** foto documental realista de personas latinas comunes de clase media, bien presentadas, con piel real y luz natural; se monta con velo azul.

El tema sale de lo que escriba el usuario, del campo `prompt_krea` de esa tarjeta o, si no hay, de una descripción que Claude escribe a partir del texto de esa tarjeta. Con **Usar en la tarjeta** la variante elegida se monta en la vista previa, las miniaturas y el PDF. Las imágenes **quedan en Krea** (tabla `ilustraciones`). Cada clic consume **saldo de API** de Krea (Krea → API → «Workspace API balance»), distinto de los créditos de la aplicación.


Para activarlo agrega en Vercel `KREA_API_TOKEN` (tipo **Sensitive**) con una clave de API de Krea de tipo **personal**, creada por el usuario dueño del modelo (las claves de servicio no ven los modelos entrenados de un usuario y Krea responde «Invalid ids detected or no access»). Luego vuelve a desplegar.

Después de agregar o cambiar variables hay que **volver a desplegar** (Deployments → ⋯ → Redeploy).

## Tarjetas de carrusel

**Rotación de colores.** Cada pieza empieza con el color de su semana (semana 1 azul marino, 2 azul, 3 gris, 4 rojo) y sus tarjetas o escenas siguen ese mismo orden; el mes siguiente vuelve a empezar en azul marino. Textos, cifras, íconos de línea y logos cambian de color para contrastar con cada fondo, y las imágenes de Krea se piden sobre el color de su tarjeta.

**Imágenes automáticas.** Al terminar los textos de un carrusel (o al rehacerlo), la app pide a Krea una imagen por tarjeta (ícono isométrico, foto e ícono de línea) y la primera que queda lista se usa en su tarjeta; las miniaturas se refrescan solas. Para cambiarlas, se entra al panel de cada tarjeta. Se desactiva con `krea.automaticas: false`. Las sugerencias de descripción usan `modelo_sugerencias` (Sonnet), más rápido. Las fotos muestran siempre eventos con tecnología (pantallas LED, gafas VR, simuladores, hologramas, pantallas táctiles, juegos multimedia, activaciones phygital).

Cada carrusel tiene el botón **Ver tarjetas**, que abre una vista previa tipo carrusel con opción de descargar el PDF: 5 páginas 4:5 en orden fijo — 1 gancho (azul marino, titular gigante en bold + ícono isométrico), 2 foto (azul, texto + foto con velo azul), 3 ícono de línea (gris), 4 dato (rojo, la primera cifra del texto gigante en bold; si no hay cifra, otra tarjeta de ícono) y 5 cierre (azul marino, comillas rojas y logos RC Farías + Constellation). La generación devuelve `diseno` con titular, texto, nota, `prompt_krea` (tarjetas 1 y 2) e `icono` (clave del ícono de línea para la tarjeta 3). Los reels usan la misma paleta y tipografías.

## Guion visual de los reels

Cada reel tiene el botón **Ver guion visual**: vista previa y descarga de un PDF 9:16 (1080 × 1920) con una página por escena (etiqueta con rol y tiempo, espacio **IMAGEN O VIDEO** y el texto en pantalla editable, dentro de la zona segura de Instagram). El diseñador lo abre en Adobe Express con «Empezar con tu contenido», inserta los medios y anima. Código en `rc/reels.py`.

Junto al texto de cada tarjeta o escena se ve su miniatura gráfica desde el principio (clic para verla en grande). **Reels.** Escena 1: ícono isométrico de Krea y su versión animada (video corto en bucle de `krea.modelo_video`, Seedance 2.0 Mini, 5 s, 720p) que se ve y descarga desde el panel «Ícono animado de la escena 1»; el PDF lleva el ícono fijo. El video parte y termina en la misma imagen (bucle) y el prompt fija el color del fondo; en la vista previa sus bordes se difuminan para fundirse con la escena. Escenas 2-4: si el texto tiene una cifra, se muestra en grande; si no, un ícono de línea de Krea basado en el texto de esa escena. Escena 5: cierre con logos, sin imagen. Las imágenes automáticas también se piden para los reels y el ícono de la escena 1 se anima solo cuando queda listo.

**Textos del reel.** Gancho hasta 8 palabras, escenas 2-4 de 9 a 15 palabras (frases completas, no telegráficas) y CTA hasta 10.

**Reel terminado.** El botón **Reel terminado** de cada reel arma el video final en el navegador (`public/reel.js`): 1080 × 1920, sin sonido; cada escena dura según su tiempo de lectura (~3 palabras por segundo + 1 s de entrada, mínimo 2,5 s; el cierre 1 s más); los textos entran palabra por palabra con un rebote, la cifra crece y cuenta hasta su valor, la escena 1 lleva el ícono animado (con el fondo del video recortado cuadro a cuadro sobre el color real de la escena; si el video no se puede procesar, con bordes fundidos) y entre escenas se elige la transición (fundido, deslizar, subir, zoom, barrido o corte; se recuerda por pieza en el navegador). «Reproducir» muestra la vista previa y «Descargar video» la graba en tiempo real con MediaRecorder (MP4 en Chrome/Edge actuales; WebM si el navegador no graba MP4). El servidor entrega cada escena sin textos y los textos con su posición (`reel-animable`), y sirve el MP4 del ícono animado (`video-icono`, hasta 4 MB) para que el navegador pueda incluirlo en la grabación. El ícono animado se genera con Kling 2.5 (sin audio) y se puede regenerar desde su panel.

**Ver reel.** En los reels, «Ver reel» y las miniaturas abren el reproductor: el reel completo en bucle (desde la escena tocada) con transiciones y textos animados; desde ahí se descarga el video o el PDF del guion. Las ventanas se cierran con clic fuera. Si un reel tiene dos o más escenas intermedias sin cifra, cada una (menos una, que conserva el ícono) puede llevar **foto con velo** del color de la escena (casilla «Usar foto en esta escena»; `piezas.diseno_reel`). En el panel de imágenes, **Borrar**, **Borrar animación** y **Borrar no usadas** quitan de la base de datos las imágenes y animaciones que no están en uso (la elegida nunca se borra; los archivos siguen en Krea).

**Números de orden.** «Paso 1», «Etapa 2», «Regla 3» o «1.» al inicio no se toman como cifra: esa escena lleva ícono (o foto). En las escenas del reel con cifra, el texto llega solo a 2/3 del ancho y crece hasta el doble (144 pt) cuando es corto, achicándose a medida que hay más texto.

**Cifra a resaltar.** Si la tarjeta de dato (carrusel: la 4) o una escena intermedia del reel tiene varias cifras, aparece «Cifra a resaltar» para elegir cuál va en grande (p. ej. en «Regla 95-5: solo 5% compra ahora»: 95-5, 95, 5 o 5%); «Automática» usa la primera. Se guarda en `piezas.diseno_reel.cifras`. El reproductor del reel tiene reproducir/pausar y una barra para adelantar o retroceder; al cambiar una transición salta a ese cambio de escena.

**Limpieza.** Al aprobarse el diseño de una pieza se borran de la base de datos las imágenes y animaciones que no se eligieron. El botón «Descargar PowerPoint» quedó oculto (la entrega es con «Descargar para publicar»).

**Aprobaciones en 3 tiempos.** 1) Reini (`OWNER_EMAIL`, administrador: puede todo) revisa investigación y textos y aprueba cada pieza. 2) Cuando las 4 piezas tienen ese aprobado, Daniela (`DISENO_EMAILS`) revisa diseños y animaciones y aprueba cada pieza (puede generar y elegir imágenes, animar, elegir cifras, fotos y música). 3) Cuando Daniela aprueba las 4, Luís (`PUBLICACION_EMAILS`) da la aprobación final y descarga. Cada etapa puede **devolver** una pieza con una nota: Luís → diseño; Daniela → textos (la nota queda como comentario para «Aplicar ajustes»). Al completarse una etapa o devolverse una pieza se avisa a Teams (`TEAMS_WEBHOOK_URL`). Daniela y Luís necesitan una cuenta en Supabase Auth con esos correos; no ven los controles de textos.

**Descarga para publicar (Luís).** Carrusel: un ZIP `Semana_N_carrusel.zip` con `Semana_N_tarjeta_01.jpg` … `05.jpg` (1080 × 1350) y `Semana_N_carrusel_LinkedIn.pdf` con todas las tarjetas (se arma en el navegador con JSZip y jsPDF). Reel: solo `Semana_N_reel.mp4`, grabado con la música elegida.

**Música del reel.** Al aprobar el diseño de un reel, la app crea 2 propuestas instrumentales (ElevenLabs Music en Krea, `krea.modelo_musica`, con la duración del reel) y pregunta si se quiere usar alguna; se escuchan antes de elegir. La elegida suena en «Ver reel» y se mezcla en el MP4 con un desvanecido al final.

**Fuentes flexibles.** La búsqueda web ya no se limita a la lista de dominios aprobados (se prefieren, pero se pueden usar otras fuentes serias). Si la fuente no es de la lista o no aparece entre los resultados de la búsqueda, la pieza muestra una **alerta** pero se puede aprobar, bajo responsabilidad de quien aprueba. `fuentes_estrictas: true` en `config/ajustes.json` vuelve al modo anterior (búsqueda limitada y bloqueo).

**Edición manual.** Doble clic sobre el texto de una tarjeta, escena o el caption (Reini, pieza sin aprobar) lo edita ahí mismo: se guarda al presionar Enter o al salir del campo, respeta el límite de palabras, se guarda como versión nueva (`edicion`) y la pieza se vuelve a validar; en los carruseles la tarjeta se vuelve a partir en titular y texto. En el caption, Enter hace un salto de párrafo y Ctrl/Cmd + Enter guarda; Esc cancela.

**Gancho.** En la tarjeta 1 de cada carrusel y la escena 1 de cada reel (pieza sin aprobar) están **Otro gancho**, que propone con IA un gancho nuevo distinto de todos los anteriores de esa pieza, y **Editar gancho**, para escribirlo a mano (Enter guarda, Esc cancela). Cada cambio se guarda como versión nueva (motivos `gancho` y `edicion`) y respeta el límite de palabras (8 en carrusel, 6 en reel); el resto del contenido no cambia.

**Detener.** Mientras una pieza se genera, rehace o ajusta, aparece **Detener**: la pieza vuelve a su versión anterior (o queda con «Reintentar» si aún no tenía contenido) y, si era un lote, no sigue con las demás. La llamada a Claude que ya estaba en curso termina en el servidor (se paga), pero su resultado se descarta y no se hacen más reparaciones. En el panel de imágenes, **Detener generación** cancela en Krea las variantes en cola (Krea no cobra las canceladas) y **Detener sugerencia** corta la sugerencia de descripción.

La vista previa (tarjetas y guion visual) tiene el botón **Rehacer**, que cambia el ícono de línea (si la tarjeta no pidió uno) o los colores de las escenas del reel sin cambiar el texto; el PDF que se descarga coincide con lo que se ve. Los recuadros de ilustración con su nota y la etiqueta de cada escena solo aparecen en la vista previa, no en el PDF descargado.

## Protección de despliegues

Vercel crea los proyectos con **Vercel Authentication** activa en todos los dominios `*.vercel.app`: para abrir la app hay que iniciar sesión en Vercel antes que en la app, y las llamadas externas de diagnóstico reciben la pantalla de Vercel en lugar de la API. Como la app tiene su propio login, se recomienda dejar la protección solo para previews: Vercel → Settings → Deployment Protection → Vercel Authentication → **Only Preview Deployments**.

## Primer usuario

1. Supabase → Authentication → Users → **Add user** → `reini@rcfarias.com` con una contraseña segura.
2. Supabase → Authentication → Sign In / Providers → desactivar **Allow new users to sign up**.

## Migraciones

En `supabase/migrations/`, aplicadas en orden:
- `001_esquema.sql`: tablas, tipos y RLS sin políticas (solo el servidor accede).
- `002_semilla_historico.sql`: los 7 temas ya publicados, como mes histórico.
- `003_configuracion.sql`: fuentes confiables (con la lista inicial de `config/fuentes.json`) y correos favoritos.
- `004_motivo_rehacer.sql`: permite el motivo «rehacer» en las versiones (botón «Rehacer propuesta»).
- `005_ilustraciones.sql`: variantes de ilustración generadas en Krea (solo enlaces y estado).
- `006_ilustracion_elegida.sql`: variante elegida por tarjeta y escena usada.
- `007_ilustracion_tarjeta_3.sql`: la tarjeta 3 (ícono de línea) también guarda variantes de Krea.
- `008_ilustracion_automatica.sql`: marca las imágenes generadas automáticamente al terminar los textos.
- `009_motivo_gancho.sql`: versiones por gancho regenerado o editado a mano.
- `010_reels_iconos_video.sql`: imágenes en las escenas del reel y video del ícono animado.
- `011_video_pedido_y_fotos_reel.sql`: hora del pedido de animación y escenas del reel con foto.
- `012_aprobaciones_por_etapa.sql`: aprobaciones de diseño y publicación, y devoluciones.

## Desarrollo local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -t .
```

## Verificación de la Fase 1

Con las variables configuradas y la app desplegada:

- `GET /api/salud` → `{"ok": true}`
- Abrir la app, ingresar con el usuario creado → "Conexión verificada".
- Prueba de Claude (genera un carrusel de prueba con búsqueda web, ~1-2 min):
  `curl -H "Authorization: Bearer $CRON_SECRET" "https://contenidos-rc.vercel.app/api/diagnostico?prueba=claude"`
