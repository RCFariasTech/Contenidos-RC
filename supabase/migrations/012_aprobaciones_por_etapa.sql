-- Aprobaciones en 3 tiempos: {"diseno": {"por": correo, "en": fecha}, "publicacion": {...}, "devolucion": {...}}.
-- La aprobación de textos (Reini) sigue siendo piezas.estado = 'aprobada'.
alter table public.piezas add column if not exists aprobaciones jsonb not null default '{}'::jsonb;
