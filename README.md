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

En las tarjetas 1 y 2 de cada carrusel, los botones **Ícono de la tarjeta 1** y **Foto de la tarjeta 2** generan 3 variantes con **Nano Banana Pro** en Krea (`config/ajustes.json` → `krea`). Los prompts de estilo están en `rc/estilo_iconos.py`:
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

Junto al texto de cada tarjeta o escena se ve su miniatura gráfica desde el principio (clic para verla en grande). **Detener.** Mientras una pieza se genera, rehace o ajusta, aparece **Detener**: la pieza vuelve a su versión anterior (o queda con «Reintentar» si aún no tenía contenido) y, si era un lote, no sigue con las demás. La llamada a Claude que ya estaba en curso termina en el servidor (se paga), pero su resultado se descarta y no se hacen más reparaciones. En el panel de imágenes, **Detener generación** cancela en Krea las variantes en cola (Krea no cobra las canceladas) y **Detener sugerencia** corta la sugerencia de descripción.

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
