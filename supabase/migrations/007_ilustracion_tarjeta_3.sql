-- La tarjeta 3 también lleva imagen de Krea (ícono de línea).
alter table public.ilustraciones drop constraint ilustraciones_tarjeta_check;
alter table public.ilustraciones add constraint ilustraciones_tarjeta_check check (tarjeta in (1, 2, 3));
