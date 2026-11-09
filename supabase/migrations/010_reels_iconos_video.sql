-- Reels: íconos de Krea en las escenas 1-4 y video (ícono isométrico animado) de la escena 1.
alter table public.ilustraciones drop constraint ilustraciones_tarjeta_check;
alter table public.ilustraciones add constraint ilustraciones_tarjeta_check check (tarjeta between 1 and 5);
alter table public.ilustraciones add column if not exists video_job_id text;
alter table public.ilustraciones add column if not exists video_estado text check (video_estado in ('en_cola', 'lista', 'fallida'));
alter table public.ilustraciones add column if not exists video_url text;
alter table public.ilustraciones add column if not exists video_error text;
