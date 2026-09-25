-- Temas ya publicados por RC Farias (PLAN.md, sección 4), cargados como mes histórico
-- para que la regla anti-repetición los considere. En meses históricos "semana" es solo un orden.
with m as (
  insert into meses (mes_objetivo, estado) values ('2000-01-01', 'historico') returning id
)
insert into piezas (mes_id, semana, formato, tipo, pilar, estado, version, contenido)
select m.id, t.orden, 'Carrusel', 'Histórico', 'Histórico', 'aprobada', 1,
       jsonb_build_object('tema_especifico', t.tema, 'semilla', true)
from m, (values
  (1, 'Cómo llegar a las nuevas generaciones'),
  (2, 'Qué es el greenwashing en las marcas'),
  (3, 'Por qué necesitas datos de tus eventos'),
  (4, 'Impacto de la IA en el BTL'),
  (5, 'Cringe marketing'),
  (6, 'BTL phygital'),
  (7, 'Marketing sensorial')
) as t(orden, tema);
