-- La variante elegida se monta en la tarjeta (vista previa y PDF); solo una por tarjeta.
-- «descripcion» guarda la escena pedida (en inglés) para poder ajustarla y volver a generar.
alter table ilustraciones add column if not exists elegida boolean not null default false;
alter table ilustraciones add column if not exists descripcion text;
create unique index if not exists ilustraciones_una_elegida on ilustraciones (pieza_id, tarjeta) where elegida;
