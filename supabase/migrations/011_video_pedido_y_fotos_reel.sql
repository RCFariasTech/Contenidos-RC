-- Hora en que se pidió la animación (el tiempo máximo se mide desde ahí) y escenas del reel con foto.
alter table public.ilustraciones add column if not exists video_pedido_en timestamptz;
alter table public.piezas add column if not exists diseno_reel jsonb not null default '{}'::jsonb;
