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
| 7. Tarjetas de carrusel | ✅ PDF 3:4 (1080 × 1440) por carrusel para diseño: texto editable, 7 estilos de la guía, espacios para ilustraciones 3D (`rc/tarjetas.py`) |

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
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys. Tipo **Sensitive** | Dueño del proyecto |

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

Después de agregar o cambiar variables hay que **volver a desplegar** (Deployments → ⋯ → Redeploy).

## Tarjetas de carrusel

Cada carrusel tiene el botón **Ver tarjetas**, que abre una vista previa tipo carrusel (flechas, teclado o deslizar) con opción de descargar el PDF: 5 páginas 3:4 con Montserrat, colores de `config/marca.json` y los logos de `plantilla/`. Solo las tarjetas 1 y 2 llevan ilustración 3D; las tarjetas 3 y 4 son solo texto y la 5 es el cierre. Los estilos rotan (distinto en cada carrusel). Las ilustraciones 3D (Krea) quedan como espacios con la nota de qué ilustrar. La generación ahora devuelve también `diseno` (titular + texto + nota por tarjeta); los carruseles generados antes no lo tienen y usan una división automática del texto hasta que se ajusten. Fuentes en `plantilla/fuentes/`.

## Guion visual de los reels

Cada reel tiene el botón **Ver guion visual**: vista previa y descarga de un PDF 9:16 (1080 × 1920) con una página por escena (etiqueta con rol y tiempo, espacio **IMAGEN O VIDEO** y el texto en pantalla editable, dentro de la zona segura de Instagram). El diseñador lo abre en Adobe Express con «Empezar con tu contenido», inserta los medios y anima. Código en `rc/reels.py`.

La vista previa (tarjetas y guion visual) tiene el botón **Rehacer**, que muestra otra propuesta de colores y estilos sin cambiar el texto; el PDF que se descarga coincide con lo que se ve. Los recuadros de ilustración con su nota y la etiqueta de cada escena solo aparecen en la vista previa, no en el PDF descargado.

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
