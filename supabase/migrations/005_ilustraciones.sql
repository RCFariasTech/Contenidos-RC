-- Variantes de ilustración 3D generadas en Krea para las tarjetas 1 y 2 de un carrusel.
-- Solo se guarda el enlace de Krea (las imágenes viven allá), el prompt usado y el estado del trabajo.
create table ilustraciones (
  id         bigint generated always as identity primary key,
  pieza_id   bigint not null references piezas(id) on delete cascade,
  tarjeta    smallint not null check (tarjeta in (1, 2)),
  job_id     text not null unique,
  prompt     text not null,
  fondo      text not null,                       -- color de fondo pedido (hex)
  ancho      int,
  alto       int,
  estado     text not null default 'en_cola' check (estado in ('en_cola', 'lista', 'fallida')),
  url        text,
  error      text,
  creado_en  timestamptz not null default now()
);
create index ilustraciones_pieza_idx on ilustraciones (pieza_id, tarjeta, creado_en desc);
alter table ilustraciones enable row level security;
