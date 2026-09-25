-- Esquema de la web app de contenido Instagram de RC Farias (ver PLAN.md, sección 4).

create type estado_mes   as enum ('generando','en_revision','aprobado','entregado','historico');
create type estado_pieza as enum ('pendiente','generando','generada','ajustando','aprobada','error');

create table meses (
  id            bigint generated always as identity primary key,
  mes_objetivo  date not null unique check (extract(day from mes_objetivo) = 1),
  estado        estado_mes not null default 'generando',
  creado_en     timestamptz not null default now(),
  aprobado_en   timestamptz,
  entregado_en  timestamptz
);

create table piezas (
  id                bigint generated always as identity primary key,
  mes_id            bigint not null references meses(id) on delete cascade,
  semana            smallint not null check (semana >= 1),  -- 1-4 en meses normales; orden libre en históricos
  fecha_publicacion date,
  formato           text not null check (formato in ('Carrusel','Reel')),
  tipo              text not null,
  pilar             text not null,
  estado            estado_pieza not null default 'pendiente',
  version           int not null default 0,
  contenido         jsonb,
  validacion        jsonb,
  uso_tokens        jsonb,
  error_msg         text,
  aprobada_en       timestamptz,
  creado_en         timestamptz not null default now(),
  actualizado_en    timestamptz not null default now(),
  unique (mes_id, semana)
);
create index piezas_mes_id_idx on piezas (mes_id);

create table versiones_pieza (
  id         bigint generated always as identity primary key,
  pieza_id   bigint not null references piezas(id) on delete cascade,
  version    int not null,
  contenido  jsonb not null,
  motivo     text not null check (motivo in ('generacion','ajuste','reparacion')),
  creado_en  timestamptz not null default now(),
  unique (pieza_id, version)
);

create table comentarios (
  id                  bigint generated always as identity primary key,
  pieza_id            bigint not null references piezas(id) on delete cascade,
  texto               text not null check (length(texto) between 1 and 2000),
  version_comentada   int not null,
  aplicado_en         timestamptz,
  version_resultante  int,
  creado_en           timestamptz not null default now()
);
create index comentarios_pieza_id_idx on comentarios (pieza_id);

-- actualizado_en automático
create function tocar_actualizado_en() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.actualizado_en := now();
  return new;
end $$;
create trigger piezas_actualizado_en before update on piezas
  for each row execute function public.tocar_actualizado_en();

-- Seguridad: RLS activado y SIN políticas. Solo la service_role (servidor) accede.
alter table meses            enable row level security;
alter table piezas           enable row level security;
alter table versiones_pieza  enable row level security;
alter table comentarios      enable row level security;
