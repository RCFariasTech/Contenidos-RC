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

Después de agregar o cambiar variables hay que **volver a desplegar** (Deployments → ⋯ → Redeploy).

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
