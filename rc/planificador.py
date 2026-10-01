"""Planificación determinista del mes: mes objetivo, slots y fechas (PLAN.md 5.2, 5.3, 10.2)."""

from datetime import date, datetime, timedelta, timezone

# Bogotá no tiene horario de verano: UTC-5 fijo (evita depender de tzdata en el servidor).
ZONA_BOGOTA = timezone(timedelta(hours=-5))

DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
               "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}


def hoy_bogota(ahora: datetime | None = None) -> date:
    return (ahora or datetime.now(timezone.utc)).astimezone(ZONA_BOGOTA).date()


def mes_siguiente(dia: date) -> date:
    return date(dia.year + (dia.month == 12), dia.month % 12 + 1, 1)


def fecha_propuesta(mes: date, semana: int, dia_semana: str) -> date:
    """N-ésimo <dia_semana> del mes (semana 1 = el primero)."""
    objetivo = DIAS_SEMANA[dia_semana.lower()]
    primero = date(mes.year, mes.month, 1)
    desfase = (objetivo - primero.weekday()) % 7
    return primero + timedelta(days=desfase + 7 * (semana - 1))


def ordenar_tipos(tipos: list[str], ultimo_uso: dict[str, date]) -> list[str]:
    """Primero los nunca usados (en el orden de la lista), luego del uso más antiguo al más reciente."""
    return sorted(tipos, key=lambda t: (t in ultimo_uso, ultimo_uso.get(t, date.min), tipos.index(t)))


def planificar(mes: date, calendario: list[dict], tipos: list[str],
               ultimo_uso_tipos: dict[str, date], dia_publicacion: str) -> list[dict]:
    """Slots del mes. Con 4 tipos y 4 piezas, cada tipo se usa una vez, empezando por los menos recientes."""
    orden = ordenar_tipos(tipos, ultimo_uso_tipos)
    slots = []
    for i, entrada in enumerate(calendario):
        slots.append({
            "semana": entrada["semana"],
            "formato": entrada["formato"],
            "pilar": entrada["pilar"],
            "tipo": orden[i % len(orden)],
            "fecha_publicacion": fecha_propuesta(mes, entrada["semana"], dia_publicacion),
        })
    return slots
