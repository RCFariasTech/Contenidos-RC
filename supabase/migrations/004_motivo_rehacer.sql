-- Permite registrar versiones creadas con «Rehacer propuesta» (tema nuevo desde cero).
alter table versiones_pieza drop constraint if exists versiones_pieza_motivo_check;
alter table versiones_pieza add constraint versiones_pieza_motivo_check
  check (motivo in ('generacion', 'ajuste', 'reparacion', 'rehacer'));
