"""Lógica de negocio de la sección "Propuestas del próximo mes" (PLAN.md, sección 5)."""

import logging
from datetime import date, datetime, timedelta, timezone

from rc import db, generador, planificador, validador
from rc.config import ajustes, pilares

log = logging.getLogger(__name__)

MINUTOS_BLOQUEO = 10  # una pieza "generando/ajustando" más tiempo que esto se considera caída


class ErrorNegocio(Exception):
    """Error esperable que se muestra tal cual al usuario (HTTP 409)."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mes_iso(mes: date) -> str:
    return mes.isoformat()


# ---------- lecturas ----------

def obtener_mes(mes: date) -> dict | None:
    filas = db.seleccionar("meses", select="*", mes_objetivo=f"eq.{_mes_iso(mes)}")
    return filas[0] if filas else None


def estado_mes(mes: date) -> dict:
    """El mes con sus piezas (ordenadas por semana) y los comentarios de cada una."""
    fila_mes = obtener_mes(mes)
    if not fila_mes:
        return {"mes_objetivo": _mes_iso(mes), "mes": None, "piezas": []}
    piezas = db.seleccionar("piezas", select="*,comentarios(*)", mes_id=f"eq.{fila_mes['id']}",
                            order="semana")
    for p in piezas:
        p["comentarios"] = sorted(p.get("comentarios") or [], key=lambda c: c["id"])
        if p.get("validacion"):
            p["validacion"].pop("urls", None)  # dato interno
    return {"mes_objetivo": _mes_iso(mes), "mes": fila_mes, "piezas": piezas}


def _pieza(pieza_id: int) -> dict:
    filas = db.seleccionar("piezas", select="*", id=f"eq.{int(pieza_id)}")
    if not filas:
        raise ErrorNegocio("La pieza no existe.")
    return filas[0]


def _contexto(pieza: dict) -> tuple[list[dict], list[dict]]:
    """(historial, hermanas) como filas {mes, pilar, contenido} para prompts y validador."""
    filas = db.seleccionar("piezas", select="id,mes_id,pilar,contenido,meses(mes_objetivo,estado)",
                           contenido="not.is.null")
    historial, hermanas = [], []
    for f in filas:
        if f["id"] == pieza["id"]:
            continue
        resumen = {"mes": (f.get("meses") or {}).get("mes_objetivo", "")[:7], "pilar": f["pilar"],
                   "contenido": f["contenido"]}
        (hermanas if f["mes_id"] == pieza["mes_id"] else historial).append(resumen)
    return historial, hermanas


def _slot(pieza: dict) -> dict:
    return {k: pieza[k] for k in ("semana", "formato", "tipo", "pilar")}


# ---------- inicio del mes ----------

def iniciar_mes(mes: date) -> dict:
    """Crea el mes y sus 4 piezas pendientes. Idempotente."""
    existente = obtener_mes(mes)
    if existente:
        return existente
    a, p = ajustes(), pilares()
    ultimo_uso: dict[str, date] = {}
    for f in db.seleccionar("piezas", select="tipo,meses(mes_objetivo,estado)"):
        m = f.get("meses") or {}
        if m.get("estado") == "historico" or f["tipo"] not in p["tipos"]:
            continue
        fecha = date.fromisoformat(m["mes_objetivo"])
        ultimo_uso[f["tipo"]] = max(fecha, ultimo_uso.get(f["tipo"], date.min))
    slots = planificador.planificar(mes, a["calendario"], p["tipos"], ultimo_uso,
                                    a["dia_publicacion_propuesto"])
    try:
        fila_mes = db.insertar("meses", {"mes_objetivo": _mes_iso(mes), "estado": "generando"})[0]
    except db.ErrorDB as e:
        if e.estado == 409:  # otra invocación lo creó a la vez
            return obtener_mes(mes)
        raise
    db.insertar("piezas", [{**s, "fecha_publicacion": s["fecha_publicacion"].isoformat(),
                            "mes_id": fila_mes["id"]} for s in slots])
    return fila_mes


# ---------- generación y ajuste ----------

def _reclamar(pieza_id: int, desde: str, hacia: str) -> dict | None:
    """Cambio de estado atómico; también rescata piezas bloqueadas por una invocación caída."""
    filas = db.actualizar("piezas", {"estado": hacia, "error_msg": None},
                          id=f"eq.{pieza_id}", estado=f"in.({desde})")
    if filas:
        return filas[0]
    limite = (datetime.now(timezone.utc) - timedelta(minutes=MINUTOS_BLOQUEO)).isoformat()
    filas = db.actualizar("piezas", {"estado": hacia, "error_msg": None}, id=f"eq.{pieza_id}",
                          estado=f"eq.{hacia}", actualizado_en=f"lt.{limite}")
    return filas[0] if filas else None


def _validar_y_reparar(pieza_fila: dict, resultado: dict, urls_validas: list[str],
                       historial: list[dict], hermanas: list[dict]) -> tuple[dict, dict, dict]:
    a = ajustes()
    contenido, uso = resultado["pieza"], dict(resultado["uso"])
    # Métricas de la llamada principal (se acumulan en uso_tokens para medir costo y tiempos)
    uso["duracion_s"] = resultado.get("duracion_s", 0)
    uso["llamadas_sin_formato_estructurado"] = 0 if resultado.get("formato_estructurado", True) else 1
    previas = [h["contenido"] for h in historial]
    otras = [h["contenido"] for h in hermanas]
    hoy = planificador.hoy_bogota()
    informe = validador.validar(pieza_fila["formato"], contenido, urls_validas, previas, otras, a, hoy)
    for _ in range(a["max_reparaciones"]):
        if not informe["reparables"]:
            break
        reparado = generador.reparar(_slot(pieza_fila), contenido, informe["reparables"])
        for k, v in reparado["uso"].items():
            uso[k] = uso.get(k, 0) + v
        uso["duracion_s"] = uso.get("duracion_s", 0) + reparado.get("duracion_s", 0)
        uso["reparaciones"] = uso.get("reparaciones", 0) + 1
        contenido = reparado["pieza"]
        informe = validador.validar(pieza_fila["formato"], contenido, urls_validas, previas, otras, a, hoy)
    return contenido, informe, uso


def _guardar_version(pieza: dict, contenido: dict, informe: dict, urls: list[str], uso: dict,
                     motivo: str) -> dict:
    version = pieza["version"] + 1
    acumulado = dict(pieza.get("uso_tokens") or {})
    for k, v in uso.items():
        acumulado[k] = acumulado.get(k, 0) + v
    fila = db.actualizar("piezas", {
        "contenido": contenido, "version": version, "estado": "generada", "error_msg": None,
        "validacion": {"errores": informe["errores"], "advertencias": informe["advertencias"],
                       "urls": urls},
        "uso_tokens": acumulado,
    }, id=f"eq.{pieza['id']}")[0]
    db.insertar("versiones_pieza", {"pieza_id": pieza["id"], "version": version,
                                    "contenido": contenido, "motivo": motivo})
    return fila


def _actualizar_estado_mes(mes_id: int) -> None:
    piezas = db.seleccionar("piezas", select="estado,contenido", mes_id=f"eq.{mes_id}")
    mes = db.seleccionar("meses", select="estado", id=f"eq.{mes_id}")[0]
    if piezas and all(p["estado"] == "aprobada" for p in piezas):
        if mes["estado"] not in ("aprobado", "entregado"):
            db.actualizar("meses", {"estado": "aprobado", "aprobado_en": _ahora()}, id=f"eq.{mes_id}")
    elif piezas and all(p["contenido"] for p in piezas):
        if mes["estado"] != "en_revision":
            db.actualizar("meses", {"estado": "en_revision"}, id=f"eq.{mes_id}")


def generar_pieza(pieza_id: int) -> dict:
    pieza = _reclamar(int(pieza_id), "pendiente,error", "generando")
    if pieza is None:
        return _pieza(pieza_id)  # otra invocación la está generando o ya está lista
    try:
        historial, hermanas = _contexto(pieza)
        resultado = generador.generar(_slot(pieza), historial, hermanas)
        urls = resultado["urls"]
        contenido, informe, uso = _validar_y_reparar(pieza, resultado, urls, historial, hermanas)
        fila = _guardar_version(pieza, contenido, informe, urls, uso, "generacion")
        _actualizar_estado_mes(pieza["mes_id"])
        return fila
    except Exception as e:
        log.exception("Fallo al generar la pieza %s", pieza_id)
        db.actualizar("piezas", {"estado": "error", "error_msg": str(e)[:500]}, id=f"eq.{pieza['id']}")
        raise


def ajustar_pieza(pieza_id: int) -> dict:
    pendientes = db.seleccionar("comentarios", select="id,texto", pieza_id=f"eq.{int(pieza_id)}",
                                aplicado_en="is.null", order="id")
    if not pendientes:
        raise ErrorNegocio("Esta pieza no tiene comentarios pendientes.")
    pieza = _reclamar(int(pieza_id), "generada", "ajustando")
    if pieza is None:
        raise ErrorNegocio("La pieza no se puede ajustar ahora (está aprobada o en proceso).")
    try:
        historial, hermanas = _contexto(pieza)
        resultado = generador.ajustar(_slot(pieza), pieza["contenido"], [c["texto"] for c in pendientes],
                                      historial, hermanas)
        urls = list(dict.fromkeys(resultado["urls"] + ((pieza.get("validacion") or {}).get("urls") or [])))
        contenido, informe, uso = _validar_y_reparar(pieza, resultado, urls, historial, hermanas)
        fila = _guardar_version(pieza, contenido, informe, urls, uso, "ajuste")
        ids = ",".join(str(c["id"]) for c in pendientes)
        db.actualizar("comentarios", {"aplicado_en": _ahora(), "version_resultante": fila["version"]},
                      id=f"in.({ids})")
        return fila
    except Exception as e:
        log.exception("Fallo al ajustar la pieza %s", pieza_id)
        db.actualizar("piezas", {"estado": "generada", "error_msg": f"El ajuste falló: {str(e)[:400]}"},
                      id=f"eq.{pieza['id']}")
        raise


# ---------- revisión ----------

def comentar(pieza_id: int, texto: str) -> dict:
    texto = (texto or "").strip()
    if not texto:
        raise ErrorNegocio("El comentario está vacío.")
    if len(texto) > 2000:
        raise ErrorNegocio("El comentario supera los 2000 caracteres.")
    pieza = _pieza(pieza_id)
    if pieza["estado"] != "generada":
        raise ErrorNegocio("Solo se puede comentar una pieza generada y sin aprobar.")
    return db.insertar("comentarios", {"pieza_id": pieza["id"], "texto": texto,
                                       "version_comentada": pieza["version"]})[0]


def borrar_comentario(comentario_id: int) -> None:
    borradas = db.borrar("comentarios", id=f"eq.{int(comentario_id)}", aplicado_en="is.null")
    if not borradas:
        raise ErrorNegocio("Solo se pueden borrar comentarios pendientes.")


def aprobar(pieza_id: int, aprobada: bool) -> dict:
    pieza = _pieza(pieza_id)
    if aprobada:
        if pieza["estado"] != "generada":
            raise ErrorNegocio("Solo se puede aprobar una pieza generada.")
        if (pieza.get("validacion") or {}).get("errores"):
            raise ErrorNegocio("La pieza tiene errores de reglas: coméntalos y aplica ajustes antes de aprobar.")
        if db.seleccionar("comentarios", select="id", pieza_id=f"eq.{pieza['id']}", aplicado_en="is.null"):
            raise ErrorNegocio("Hay comentarios pendientes: aplica los ajustes o bórralos antes de aprobar.")
        fila = db.actualizar("piezas", {"estado": "aprobada", "aprobada_en": _ahora()},
                             id=f"eq.{pieza['id']}", estado="eq.generada")
    else:
        fila = db.actualizar("piezas", {"estado": "generada", "aprobada_en": None},
                             id=f"eq.{pieza['id']}", estado="eq.aprobada")
        mes = db.seleccionar("meses", select="estado", id=f"eq.{pieza['mes_id']}")[0]
        if mes["estado"] in ("aprobado", "entregado"):
            db.actualizar("meses", {"estado": "en_revision"}, id=f"eq.{pieza['mes_id']}")
    if not fila:
        raise ErrorNegocio("La pieza cambió de estado; recarga la página.")
    _actualizar_estado_mes(pieza["mes_id"])
    return fila[0]


def cambiar_fecha(pieza_id: int, fecha: str) -> dict:
    try:
        dia = date.fromisoformat(fecha)
    except (TypeError, ValueError) as e:
        raise ErrorNegocio("Fecha inválida (usa AAAA-MM-DD).") from e
    filas = db.actualizar("piezas", {"fecha_publicacion": dia.isoformat()}, id=f"eq.{int(pieza_id)}",
                          estado="not.in.(generando,ajustando)")
    if not filas:
        raise ErrorNegocio("No se puede cambiar la fecha mientras la pieza se procesa.")
    return filas[0]
