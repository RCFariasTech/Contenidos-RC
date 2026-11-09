-- Nuevas versiones al regenerar el gancho con IA ('gancho') o al editarlo a mano ('edicion').
alter table public.versiones_pieza drop constraint versiones_pieza_motivo_check;
alter table public.versiones_pieza add constraint versiones_pieza_motivo_check
  check (motivo in ('generacion', 'ajuste', 'reparacion', 'rehacer', 'gancho', 'edicion'));
