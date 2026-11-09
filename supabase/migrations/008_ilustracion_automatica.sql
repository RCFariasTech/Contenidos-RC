-- Imágenes que la app pide sola al terminar los textos de un carrusel; la primera que queda lista se usa en su tarjeta.
alter table public.ilustraciones add column if not exists automatica boolean not null default false;
