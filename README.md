# Contenido Instagram RC Farias

Web app privada para generar, revisar, ajustar y aprobar el contenido mensual de Instagram de RC Farias, y exportarlo a PowerPoint. El diseño completo está en [`PLAN.md`](PLAN.md).

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
