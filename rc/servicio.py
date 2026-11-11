"""Lógica de negocio de la sección "Propuestas del próximo mes" (PLAN.md, sección 5)."""

import logging
from datetime import date, datetime, timedelta, timezone

from rc import db, fuentes, generador, krea, planificador, teams, validador
from rc.config import ajustes, env, pilares
from rc.errores import ErrorNegocio  # noqa: F401 (se reexporta: servicio.ErrorNegocio)

log = logging.getLogger(__name__)

MINUTOS_BLOQUEO = 10  # una pieza "generando/ajustando" más tiempo que esto se considera caída


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

class Detenida(ErrorNegocio):
    """El usuario detuvo la generación: el resultado se descarta sin tocar el estado que dejó «Detener»."""


EN_PROCESO = "generando,ajustando"


def _sigue_activa(pieza_id: int) -> None:
    """Corta el trabajo (antes de cada llamada costosa) si el usuario lo detuvo."""
    if not db.seleccionar("piezas", select="id", id=f"eq.{int(pieza_id)}", estado=f"in.({EN_PROCESO})"):
        raise Detenida("Generación detenida.")


def detener_pieza(pieza_id: int) -> dict:
    """Detiene la generación, el rehacer o el ajuste en curso: la pieza vuelve a su última versión (o queda para
    reintentar si aún no tenía contenido). Lo que esté calculando el servidor se descarta al terminar."""
    pieza = _pieza(int(pieza_id))
    nuevo = ({"estado": "generada", "error_msg": "Detuviste la generación; se conserva la versión anterior."}
             if pieza.get("contenido") else
             {"estado": "error", "error_msg": "Detuviste la generación. Pulsa «Reintentar» cuando quieras generarla."})
    filas = db.actualizar("piezas", nuevo, id=f"eq.{pieza['id']}", estado=f"in.({EN_PROCESO})")
    if not filas:
        raise ErrorNegocio("Esta pieza no se está generando.")
    return filas[0]


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
    informe = validador.validar(pieza_fila["formato"], contenido, urls_validas, previas, otras, a, hoy, fuentes.dominios())
    for _ in range(a["max_reparaciones"]):
        if not informe["reparables"]:
            break
        _sigue_activa(pieza_fila["id"])
        reparado = generador.reparar(_slot(pieza_fila), contenido, informe["reparables"])
        for k, v in reparado["uso"].items():
            uso[k] = uso.get(k, 0) + v
        uso["duracion_s"] = uso.get("duracion_s", 0) + reparado.get("duracion_s", 0)
        uso["reparaciones"] = uso.get("reparaciones", 0) + 1
        contenido = reparado["pieza"]
        informe = validador.validar(pieza_fila["formato"], contenido, urls_validas, previas, otras, a, hoy, fuentes.dominios())
    return contenido, informe, uso


def _guardar_version(pieza: dict, contenido: dict, informe: dict, urls: list[str], uso: dict,
                     motivo: str) -> dict:
    version = pieza["version"] + 1
    acumulado = dict(pieza.get("uso_tokens") or {})
    for k, v in uso.items():
        acumulado[k] = acumulado.get(k, 0) + v
    filas = db.actualizar("piezas", {
        "contenido": contenido, "version": version, "estado": "generada", "error_msg": None,
        "validacion": {"errores": informe["errores"], "advertencias": informe["advertencias"],
                       "urls": urls},
        "uso_tokens": acumulado,
    }, id=f"eq.{pieza['id']}", estado=f"in.({EN_PROCESO})")  # si el usuario la detuvo, no se guarda
    if not filas:
        raise Detenida("Generación detenida.")
    fila = filas[0]
    db.insertar("versiones_pieza", {"pieza_id": pieza["id"], "version": version,
                                    "contenido": contenido, "motivo": motivo})
    return fila


def _actualizar_estado_mes(mes_id: int) -> None:
    piezas = db.seleccionar("piezas", select="estado,contenido", mes_id=f"eq.{mes_id}")
    mes = db.seleccionar("meses", select="estado,mes_objetivo", id=f"eq.{mes_id}")[0]
    if piezas and all(p["estado"] == "aprobada" for p in piezas):
        if mes["estado"] not in ("aprobado", "entregado"):  # re-aprobar tras un cambio vuelve a "aprobado"
            db.actualizar("meses", {"estado": "aprobado", "aprobado_en": _ahora()}, id=f"eq.{mes_id}")
    elif piezas and all(p["contenido"] for p in piezas):
        if mes["estado"] == "generando":
            # Condicional: si dos piezas terminan a la vez, solo una pasa el mes a revisión y avisa a Teams.
            if db.actualizar("meses", {"estado": "en_revision"}, id=f"eq.{mes_id}", estado="eq.generando"):
                teams.avisar_revision(mes["mes_objetivo"], len(piezas))
        elif mes["estado"] != "en_revision":
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
        imagenes_automaticas(pieza["id"])
        return fila
    except Detenida:
        raise
    except Exception as e:
        log.exception("Fallo al generar la pieza %s", pieza_id)
        db.actualizar("piezas", {"estado": "error", "error_msg": str(e)[:500]}, id=f"eq.{pieza['id']}")
        raise


def rehacer_pieza(pieza_id: int) -> dict:
    """Descarta la propuesta actual y genera otra desde cero: tema, investigación y textos nuevos."""
    pieza_id = int(pieza_id)
    if db.seleccionar("comentarios", select="id", pieza_id=f"eq.{pieza_id}", aplicado_en="is.null"):
        raise ErrorNegocio("Esta pieza tiene comentarios pendientes: aplícalos con «Aplicar ajustes» o bórralos antes de rehacerla.")
    pieza = _reclamar(pieza_id, "generada", "generando")
    if pieza is None:
        raise ErrorNegocio("La pieza no se puede rehacer ahora (está aprobada o en proceso).")
    try:
        historial, hermanas = _contexto(pieza)
        # Todos los temas que esta pieza ya tuvo (incluida la propuesta actual) se descartan y cuentan como repetidos.
        previos = db.seleccionar("versiones_pieza", select="contenido", pieza_id=f"eq.{pieza_id}", order="version")
        descartados = [{"mes": "", "pilar": pieza["pilar"], "contenido": v["contenido"]} for v in previos]
        resultado = generador.generar(_slot(pieza), historial, hermanas + descartados, descartados)
        urls = resultado["urls"]
        contenido, informe, uso = _validar_y_reparar(pieza, resultado, urls, historial, hermanas + descartados)
        fila = _guardar_version(pieza, contenido, informe, urls, uso, "rehacer")
        # Tema nuevo: las imágenes del tema anterior ya no aplican; se piden otras.
        db.actualizar("ilustraciones", {"elegida": False}, pieza_id=f"eq.{pieza_id}", elegida="is.true")
        imagenes_automaticas(pieza_id)
        return fila
    except Detenida:
        raise
    except Exception as e:
        log.exception("Fallo al rehacer la pieza %s", pieza_id)
        db.actualizar("piezas", {"estado": "generada", "error_msg": f"No se pudo rehacer la propuesta: {str(e)[:400]}"},
                      id=f"eq.{pieza_id}")
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
    except Detenida:
        raise
    except Exception as e:
        log.exception("Fallo al ajustar la pieza %s", pieza_id)
        db.actualizar("piezas", {"estado": "generada", "error_msg": f"El ajuste falló: {str(e)[:400]}"},
                      id=f"eq.{pieza['id']}")
        raise


# ---------- gancho ----------

CAMPO_GANCHO = {"Carrusel": "slide_1_gancho", "Reel": "escena_1_gancho"}


CAMPOS_EDITABLES = {
    "Carrusel": ("slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre", "caption"),
    "Reel": ("escena_1_gancho", "escena_2_desarrollo_a", "escena_3_desarrollo_b", "escena_4_desarrollo_c",
             "escena_5_cta", "caption"),
}


def _cambiar_texto(pieza_id: int, campo: str, texto: str, motivo: str) -> dict:
    """Guarda una versión nueva con un texto cambiado (tarjeta, escena o caption); el resto queda igual y la pieza
    se vuelve a validar (las reglas incumplidas aparecen como siempre)."""
    from rc import tarjetas
    pieza = _pieza(int(pieza_id))
    if campo not in CAMPOS_EDITABLES[pieza["formato"]]:
        raise ErrorNegocio("Ese texto no se puede editar.")
    texto = (texto or "").strip() if campo == "caption" else " ".join((texto or "").split())
    nombre = "El caption" if campo == "caption" else "El texto"
    if not texto:
        raise ErrorNegocio(f"{nombre} no puede quedar vacío.")
    a = ajustes()
    maximo = a["max_palabras_caption"] if campo == "caption" else validador.LIMITES[pieza["formato"]][campo]
    palabras = len(texto.split())
    if palabras > maximo:
        raise ErrorNegocio(f"{nombre} tiene {palabras} palabras; el máximo es {maximo}.")
    if texto == (pieza.get("contenido") or {}).get(campo):
        raise ErrorNegocio(f"{nombre} no cambió.")
    reclamada = _reclamar(pieza["id"], "generada", "ajustando")
    if reclamada is None:
        raise ErrorNegocio("No se puede editar ahora (la pieza está aprobada o en proceso).")
    try:
        contenido = {**reclamada["contenido"], campo: texto}
        if contenido.get("diseno") and campo in tarjetas.CAMPOS_SLIDE:
            # La tarjeta se vuelve a partir en titular + texto: la 1 todo titular, la 5 todo texto, las demás en su
            # primera oración (o hasta los dos puntos).
            i = tarjetas.CAMPOS_SLIDE.index(campo)
            diseno = [dict(d) for d in contenido["diseno"]]
            if i == 0:
                diseno[0].update(titular=texto, texto="")
            elif i == len(tarjetas.CAMPOS_SLIDE) - 1:
                diseno[i].update(titular="", texto=texto)
            else:
                titular, resto = tarjetas._separar(texto)
                diseno[i].update(titular=titular, texto=resto)
            contenido["diseno"] = diseno
        validacion = reclamada.get("validacion") or {}
        urls = validacion.get("urls", [])
        historial, hermanas = _contexto(reclamada)
        informe = validador.validar(reclamada["formato"], contenido, urls, [h["contenido"] for h in historial],
                                    [h["contenido"] for h in hermanas], a, planificador.hoy_bogota(), fuentes.dominios())
        return _guardar_version(reclamada, contenido, informe, urls, {}, motivo)
    except Detenida:
        raise
    except Exception:
        db.actualizar("piezas", {"estado": "generada"}, id=f"eq.{pieza['id']}", estado="eq.ajustando")
        raise


def _cambiar_gancho(pieza_id: int, gancho: str, motivo: str) -> dict:
    pieza = _pieza(int(pieza_id))
    return _cambiar_texto(pieza["id"], CAMPO_GANCHO[pieza["formato"]], gancho, motivo)


def editar_texto(pieza_id: int, campo: str, texto: str) -> dict:
    return _cambiar_texto(pieza_id, campo, texto, "edicion")


def regenerar_gancho(pieza_id: int) -> dict:
    """Propone con IA un gancho nuevo, distinto de todos los que ya tuvo la pieza, y lo guarda como versión."""
    pieza = _pieza(int(pieza_id))
    if pieza["estado"] != "generada" or not pieza.get("contenido"):
        raise ErrorNegocio("El gancho no se puede cambiar ahora (la pieza está aprobada o en proceso).")
    campo = CAMPO_GANCHO[pieza["formato"]]
    previos = [v["contenido"].get(campo, "") for v in
               db.seleccionar("versiones_pieza", select="contenido", pieza_id=f"eq.{pieza['id']}", order="version")]
    evitar = list(dict.fromkeys([pieza["contenido"].get(campo, "")] + previos))
    try:
        gancho = generador.proponer_gancho(pieza["formato"], pieza["contenido"], evitar,
                                           validador.LIMITES[pieza["formato"]][campo])
    except generador.ErrorGeneracion as e:
        raise ErrorNegocio(str(e)) from e
    maximo = validador.LIMITES[pieza["formato"]][campo]
    gancho = " ".join(gancho.split()[:maximo])  # por si el modelo se pasa del límite
    return _cambiar_gancho(pieza["id"], gancho, "gancho")


def editar_gancho(pieza_id: int, gancho: str) -> dict:
    return _cambiar_gancho(pieza_id, gancho, "edicion")


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
    if aprobada:
        _avisar_si_etapa_completa(pieza["mes_id"], "textos")
    else:  # al reabrir los textos, las aprobaciones de diseño y publicación ya no valen
        fila = db.actualizar("piezas", {"aprobaciones": {}}, id=f"eq.{pieza['id']}") or fila
    _actualizar_estado_mes(pieza["mes_id"])
    return fila[0]


# ---------- música del reel (Krea · ElevenLabs Music, solo instrumental) ----------

PROMPTS_MUSICA = (
    "Modern, upbeat tech-startup instrumental for a short brand video: driving electronic beat, bright synth plucks, "
    "punchy drums, optimistic and dynamic, around 120 BPM, clean modern mix, clear intro and a clean ending. "
    "Instrumental only, no vocals.",
    "Energetic future-house instrumental for a technology product reel: groovy bassline, crisp claps, airy pads and a "
    "catchy synth hook, motivational and modern, around 115 BPM, polished mix with a clean ending. "
    "Instrumental only, no vocals.",
)


def _musica(pieza: dict) -> dict:
    return dict((pieza.get("diseno_reel") or {}).get("musica") or {})


def _guardar_musica(pieza: dict, musica: dict) -> None:
    db.actualizar("piezas", {"diseno_reel": {**(pieza.get("diseno_reel") or {}), "musica": musica}},
                  id=f"eq.{pieza['id']}")


def generar_musica(pieza_id: int) -> dict:
    """Pide a Krea dos propuestas de música instrumental con la duración del reel."""
    from rc import reels
    pieza = _pieza(int(pieza_id))
    if pieza["formato"] != "Reel" or not pieza.get("contenido"):
        raise ErrorNegocio("La música es para reels con contenido.")
    if not krea.configurado():
        raise ErrorNegocio("Krea no está activado: falta KREA_API_TOKEN en Vercel.")
    ms = int(sum(reels.duraciones(pieza["contenido"])) * 1000) + 1000
    opciones = []
    for prompt in PROMPTS_MUSICA:
        opciones.append({"job_id": krea.crear_audio(prompt, ms), "estado": "en_cola", "url": None, "error": None})
    musica = {"opciones": opciones, "elegida": None, "pedida_en": _ahora()}
    _guardar_musica(pieza, musica)
    return musica


def estado_musica(pieza_id: int) -> dict:
    """Propuestas de música con su estado (consulta a Krea las que siguen en cola)."""
    pieza = _pieza(int(pieza_id))
    musica = _musica(pieza)
    cambio = False
    for o in musica.get("opciones", []):
        if o["estado"] == "en_cola":
            try:
                nuevo = krea.consultar(o["job_id"])
            except ErrorNegocio:
                continue
            if nuevo["estado"] != "en_cola":
                o.update(nuevo)
                cambio = True
    if cambio:
        _guardar_musica(pieza, musica)
    return musica


def elegir_musica(pieza_id: int, indice) -> dict:
    pieza = _pieza(int(pieza_id))
    musica = _musica(pieza)
    if indice is not None:
        indice = int(indice)
        opciones = musica.get("opciones") or []
        if not (0 <= indice < len(opciones)) or opciones[indice]["estado"] != "lista":
            raise ErrorNegocio("Esa propuesta de música no está lista.")
    musica["elegida"] = indice
    _guardar_musica(pieza, musica)
    return musica


def musica_audio(pieza_id: int, indice=None) -> bytes:
    """El audio (de la propuesta `indice` o de la elegida), servido desde la app para mezclarlo en el reel."""
    import urllib.parse
    import urllib.request
    musica = _musica(_pieza(int(pieza_id)))
    indice = musica.get("elegida") if indice is None else int(indice)
    opciones = musica.get("opciones") or []
    if indice is None or not (0 <= indice < len(opciones)) or not str(opciones[indice].get("url") or "").startswith("https://"):
        raise ErrorNegocio("No hay música elegida.")
    url = opciones[indice]["url"]
    host = urllib.parse.urlparse(url).hostname or ""
    if not (host == "krea.ai" or host.endswith(".krea.ai")):
        raise ErrorNegocio("El audio no viene de Krea.")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "contenidos-rc"}), timeout=25) as r:
            datos = r.read(MAX_BYTES_VIDEO + 1)
    except Exception as e:  # noqa: BLE001
        raise ErrorNegocio("No se pudo descargar la música de Krea.") from e
    if len(datos) > MAX_BYTES_VIDEO:
        raise ErrorNegocio("La música pesa demasiado para servirla desde la app.")
    return datos


def tarjeta_jpg(pieza_id: int, numero: int) -> tuple[str, bytes]:
    """Una tarjeta del carrusel en JPG 1080 x 1350, para la descarga por lotes («Semana_1_tarjeta_01.jpg»)."""
    import pymupdf
    pieza = _pieza(int(pieza_id))
    if pieza["formato"] != "Carrusel":
        raise ErrorNegocio("La descarga por tarjetas es para carruseles.")
    _nombre, pdf = tarjetas_pdf(pieza["id"], 0, guias=False)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        numero = int(numero)
        if not 1 <= numero <= len(doc):
            raise ErrorNegocio("Esa tarjeta no existe.")
        pagina = doc[numero - 1]
        jpg = pagina.get_pixmap(matrix=pymupdf.Matrix(1080 / pagina.rect.width, 1080 / pagina.rect.width)).tobytes(
            "jpg", jpg_quality=92)
    return f"Semana_{pieza['semana']}_tarjeta_{numero:02d}.jpg", jpg


# ---------- aprobaciones en 3 tiempos: textos (Reini) → diseño (Daniela) → publicación (Luís) ----------

ETAPAS = ("textos", "diseno", "publicacion")
SIGUIENTE = {"textos": ("Daniela", "revisión de diseños y animaciones"),
             "diseno": ("Luís", "aprobación final y descarga para publicar"),
             "publicacion": (None, "")}


def _aprobada_en(pieza: dict, etapa: str) -> bool:
    if etapa == "textos":
        return pieza["estado"] == "aprobada"
    return bool((pieza.get("aprobaciones") or {}).get(etapa))


def _piezas_mes(mes_id: int) -> list[dict]:
    return db.seleccionar("piezas", select="*", mes_id=f"eq.{mes_id}", order="semana")


def etapa_completa(mes_id: int, etapa: str) -> bool:
    piezas = _piezas_mes(mes_id)
    return bool(piezas) and all(_aprobada_en(p, etapa) for p in piezas)


def _avisar_si_etapa_completa(mes_id: int, etapa: str) -> None:
    if not etapa_completa(mes_id, etapa):
        return
    mes = db.seleccionar("meses", select="mes_objetivo", id=f"eq.{mes_id}")[0]["mes_objetivo"]
    persona, que = SIGUIENTE[etapa]
    nombres = {"textos": "Textos aprobados", "diseno": "Diseños aprobados", "publicacion": "Listo para publicar"}
    texto = (f"Todas las piezas pasaron esta etapa. Ahora sigue {persona}: {que}." if persona
             else "Luís aprobó todas las piezas: ya se pueden descargar y publicar.")
    teams.avisar_etapa(mes, nombres[etapa], texto)


def _limpiar_no_elegidas(pieza_id: int) -> int:
    """Diseño aprobado: borra las imágenes y animaciones que no se eligieron (no ocupan espacio en Supabase).
    Nunca hace fallar la aprobación."""
    borradas = 0
    tarjetas_con_imagenes = {int(f["tarjeta"]) for f in
                             db.seleccionar("ilustraciones", select="tarjeta", pieza_id=f"eq.{int(pieza_id)}")}
    for tarjeta in sorted(tarjetas_con_imagenes):
        try:
            borradas += borrar_ilustraciones(pieza_id, tarjeta)["borradas"]
        except Exception:  # noqa: BLE001
            log.warning("No se pudieron borrar las imágenes no usadas de la tarjeta %s", tarjeta, exc_info=True)
    return borradas


def aprobar_etapa(pieza_id: int, etapa: str, aprobada: bool, usuario: dict) -> dict:
    """Aprueba (o quita la aprobación de) la etapa de diseño o de publicación de una pieza. Cada etapa se abre
    cuando TODAS las piezas del mes pasaron la anterior."""
    if etapa not in ("diseno", "publicacion"):
        raise ErrorNegocio("Etapa desconocida.")
    pieza = _pieza(int(pieza_id))
    previa = ETAPAS[ETAPAS.index(etapa) - 1]
    aprob = dict(pieza.get("aprobaciones") or {})
    if aprobada:
        if not etapa_completa(pieza["mes_id"], previa):
            quien = "Reini (textos)" if previa == "textos" else "Daniela (diseño)"
            raise ErrorNegocio(f"Esta etapa se abre cuando {quien} haya aprobado las 4 piezas.")
        aprob[etapa] = {"por": usuario.get("email"), "en": _ahora()}
        aprob.pop("devolucion", None)
    else:
        aprob.pop(etapa, None)
        if etapa == "diseno":
            aprob.pop("publicacion", None)
    fila = db.actualizar("piezas", {"aprobaciones": aprob}, id=f"eq.{pieza['id']}")[0]
    if aprobada and etapa == "diseno":
        _limpiar_no_elegidas(pieza["id"])
    if aprobada:
        _avisar_si_etapa_completa(pieza["mes_id"], etapa)
    return fila


def devolver(pieza_id: int, nota: str, usuario: dict) -> dict:
    """Devuelve la pieza a la etapa anterior con una nota: desde publicación vuelve a diseño (Daniela); desde diseño
    vuelve a textos (Reini), y la nota queda como comentario para aplicar con «Aplicar ajustes»."""
    pieza = _pieza(int(pieza_id))
    nota = " ".join((nota or "").split())[:1000]
    if not nota:
        raise ErrorNegocio("Escribe qué hay que corregir.")
    aprob = dict(pieza.get("aprobaciones") or {})
    rol = usuario.get("rol")
    a_diseno = rol == "publicacion" or (rol == "admin" and aprob.get("diseno"))
    quien = usuario.get("email") or ""
    if a_diseno:
        aprob.pop("diseno", None)
        aprob.pop("publicacion", None)
        aprob["devolucion"] = {"a": "diseno", "por": quien, "en": _ahora(), "nota": nota}
        fila = db.actualizar("piezas", {"aprobaciones": aprob}, id=f"eq.{pieza['id']}")[0]
        destino = "Daniela (diseño)"
    else:
        aprob = {"devolucion": {"a": "textos", "por": quien, "en": _ahora(), "nota": nota}}
        db.actualizar("piezas", {"estado": "generada", "aprobada_en": None}, id=f"eq.{pieza['id']}",
                      estado="eq.aprobada")
        fila = db.actualizar("piezas", {"aprobaciones": aprob}, id=f"eq.{pieza['id']}")[0]
        db.insertar("comentarios", {"pieza_id": pieza["id"], "texto": f"[Devuelta por {quien}] {nota}",
                                    "version_comentada": pieza["version"]})
        destino = "Reini (textos)"
        _actualizar_estado_mes(pieza["mes_id"])
    mes = db.seleccionar("meses", select="mes_objetivo", id=f"eq.{pieza['mes_id']}")[0]["mes_objetivo"]
    teams.avisar_etapa(mes, f"Pieza devuelta a {destino}",
                       f"Semana {pieza['semana']} · {pieza['formato']}: {nota}")
    return fila


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


# ---------- exportación ----------

def _variante(pieza: dict) -> tuple[str, int]:
    """(mes_objetivo, variante): cambia de una pieza a otra y de un mes a otro, así los colores del feed rotan."""
    mes = db.seleccionar("meses", select="mes_objetivo", id=f"eq.{pieza['mes_id']}")[0]["mes_objetivo"]
    mismas = db.seleccionar("piezas", select="id", mes_id=f"eq.{pieza['mes_id']}",
                            formato=f"eq.{pieza['formato']}", order="semana")
    return mes, int(mes[5:7]) * 2 + [c["id"] for c in mismas].index(pieza["id"])


def tarjetas_pdf(pieza_id: int, semilla: int = 0, guias: bool = False) -> tuple[str, bytes]:
    """PDF para diseño: las 5 tarjetas 4:5 de un carrusel o el guion visual 9:16 de un reel."""
    from rc import reels, tarjetas  # import diferido: reportlab/svglib solo se cargan al generar
    pieza = _pieza(pieza_id)
    if not pieza.get("contenido"):
        raise ErrorNegocio("Esta pieza aún no tiene contenido.")
    mes, variante = _variante(pieza)
    contenido = pieza["contenido"]
    inicio = tarjetas.inicio_de_semana(pieza.get("semana"))  # color con que empieza la pieza: rota por semana
    titulo = f"{'Reel' if pieza['formato'] == 'Reel' else 'Carrusel'} · {contenido.get('tema_especifico', '')}"
    if pieza["formato"] == "Reel":
        modulo = reels
        pdf = reels.generar_pdf(contenido, titulo, inicio, semilla=max(0, int(semilla)), guias=guias,
                                imagenes=_imagenes_elegidas(pieza["id"]), fotos=_fotos_reel(pieza),
                                cifras=_cifras(pieza))
    else:
        modulo = tarjetas
        pdf = tarjetas.generar_pdf(contenido, titulo, variante, semilla=max(0, int(semilla)), guias=guias,
                                   imagenes=_imagenes_elegidas(pieza["id"]), inicio=inicio, cifras=_cifras(pieza))
    return modulo.nombre_archivo(contenido, mes), pdf


def vista_tarjetas(pieza_id: int, semilla: int = 0, ancho: int = 720) -> dict:
    """Las páginas como imágenes PNG (data URI) para la vista previa tipo carrusel, y su relación de aspecto."""
    import base64
    from rc import tarjetas
    pieza = _pieza(pieza_id)
    _nombre, pdf = tarjetas_pdf(pieza_id, semilla, guias=True)
    imagenes = ["data:image/png;base64," + base64.b64encode(png).decode() for png in tarjetas.imagenes_png(pdf, max(200, min(int(ancho), 900)))]
    # Imágenes automáticas que Krea aún no termina: la pantalla vuelve a pedir la vista en unos segundos.
    en_cola = len(db.seleccionar("ilustraciones", select="id", pieza_id=f"eq.{int(pieza_id)}", automatica="is.true",
                                 estado="eq.en_cola"))
    respuesta = {"imagenes": imagenes, "relacion": 9 / 16 if pieza["formato"] == "Reel" else 4 / 5,
                 "imagenes_en_cola": en_cola}
    if pieza["formato"] == "Reel":
        # Animación del ícono de la escena 1: la pantalla la superpone sobre la imagen, en la posición del ícono.
        filas = db.seleccionar("ilustraciones", select="video_url,video_estado", pieza_id=f"eq.{int(pieza_id)}",
                               tarjeta="eq.1", elegida="is.true")
        video = next((f["video_url"] for f in filas if f.get("video_estado") == "lista"
                      and str(f.get("video_url") or "").startswith("https://")), None)
        if video:
            from rc import reels
            x, y, lado = reels.caja_icono(pieza["contenido"])
            respuesta["video_escena_1"] = {"url": video, "x": x / reels.W, "y": y / reels.H,
                                           "ancho": lado / reels.W, "alto": lado / reels.H}
        respuesta["video_en_cola"] = any(f.get("video_estado") == "en_cola" for f in filas)
    return respuesta


MAX_BYTES_VIDEO = 4 * 1024 * 1024  # límite de respuesta de las funciones de Vercel (~4,5 MB)


def video_icono(pieza_id: int) -> bytes:
    """El MP4 del ícono animado elegido de la escena 1, servido desde la app: así el navegador puede grabarlo dentro
    del reel (los videos de Krea no permiten usarse en un lienzo desde otro dominio)."""
    import urllib.parse
    import urllib.request
    filas = db.seleccionar("ilustraciones", select="video_url,video_estado", pieza_id=f"eq.{int(pieza_id)}",
                           tarjeta="eq.1", elegida="is.true", video_estado="eq.lista")
    url = next((f["video_url"] for f in filas if str(f.get("video_url") or "").startswith("https://")), None)
    if not url:
        raise ErrorNegocio("Esta pieza no tiene ícono animado listo.")
    host = urllib.parse.urlparse(url).hostname or ""
    if not (host == "krea.ai" or host.endswith(".krea.ai")):
        raise ErrorNegocio("El video no viene de Krea.")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "contenidos-rc"}), timeout=25) as r:
            datos = r.read(MAX_BYTES_VIDEO + 1)
    except Exception as e:  # noqa: BLE001
        raise ErrorNegocio("No se pudo descargar el video de Krea.") from e
    if len(datos) > MAX_BYTES_VIDEO:
        raise ErrorNegocio("El video del ícono pesa demasiado para servirlo desde la app.")
    return datos


def reel_animable(pieza_id: int) -> dict:
    """Datos para armar el reel terminado en la pantalla: fondo de cada escena sin textos, textos con su posición y
    el video del ícono animado de la escena 1 (si está listo)."""
    from rc import reels, tarjetas
    pieza = _pieza(int(pieza_id))
    if pieza["formato"] != "Reel" or not pieza.get("contenido"):
        raise ErrorNegocio("El video terminado es para reels con contenido.")
    inicio = tarjetas.inicio_de_semana(pieza.get("semana"))
    imagenes = _imagenes_elegidas(pieza["id"])  # también actualiza imágenes y videos que seguían en Krea
    escenas = reels.escenas_animables(pieza["contenido"], inicio, imagenes, fotos=_fotos_reel(pieza),
                                      cifras=_cifras(pieza))
    filas = db.seleccionar("ilustraciones", select="video_url,video_estado", pieza_id=f"eq.{pieza['id']}",
                           tarjeta="eq.1", elegida="is.true")
    video = next((f["video_url"] for f in filas if f.get("video_estado") == "lista"
                  and str(f.get("video_url") or "").startswith("https://")), None)
    musica = _musica(pieza)
    respuesta = {"ancho": reels.W, "alto": reels.H, "escenas": escenas, "video_escena_1": None,
                 "tema": pieza["contenido"].get("tema_especifico", ""), "semana": pieza.get("semana"),
                 "musica": musica.get("elegida") is not None}
    if video:
        x, y, lado = reels.caja_icono(pieza["contenido"])
        respuesta["video_escena_1"] = {"url": video, "x": x, "y": y, "lado": lado}
        # Fondo de la escena 1 sin el ícono fijo, para poner encima el animado con su fondo recortado.
        sin_icono = {k: v for k, v in imagenes.items() if k != 1}
        respuesta["fondo_escena_1_sin_icono"] = reels.escenas_animables(
            pieza["contenido"], inicio, sin_icono, fotos=_fotos_reel(pieza), cifras=_cifras(pieza))[0]["fondo"]
    return respuesta


# ---------- ilustraciones 3D (Krea) ----------

MINUTOS_MAX_ILUSTRACION = 10


def _texto_tarjeta(contenido: dict, tarjeta: int) -> dict:
    """Titular, texto y nota de la tarjeta (usa `diseno` o, en contenidos viejos, la división automática)."""
    from rc import tarjetas
    return tarjetas.datos_tarjetas(contenido)[tarjeta - 1]


def _cifras(pieza: dict) -> dict:
    """{"tarjeta o escena": cifra elegida para resaltar} (se guarda en piezas.diseno_reel, también en carruseles)."""
    return dict((pieza.get("diseno_reel") or {}).get("cifras") or {})


def elegir_cifra(pieza_id: int, numero: int, cifra: str) -> dict:
    """Elige qué cifra resaltar cuando una tarjeta (carrusel: la 4) o escena (reel: 2-4) tiene varias.
    Cifra vacía vuelve a la automática (la primera del texto)."""
    from rc import reels, tarjetas
    pieza = _pieza(int(pieza_id))
    numero = int(numero)
    if not pieza.get("contenido"):
        raise ErrorNegocio("Esta pieza aún no tiene contenido.")
    if pieza["formato"] == "Reel":
        if numero not in (2, 3, 4):
            raise ErrorNegocio("Solo las escenas 2 a 4 resaltan cifras.")
        texto = pieza["contenido"].get(reels.CAMPOS[numero - 1], "")
    else:
        if numero != 4:
            raise ErrorNegocio("En los carruseles, la cifra se resalta en la tarjeta 4.")
        texto = tarjetas.datos_tarjetas(pieza["contenido"])[3]["completo"]
    cifra = " ".join((cifra or "").split())
    if cifra and cifra not in tarjetas.candidatos_cifra(texto):
        raise ErrorNegocio("Esa cifra no está en el texto.")
    cifras = _cifras(pieza)
    if cifra:
        cifras[str(numero)] = cifra
    else:
        cifras.pop(str(numero), None)
    db.actualizar("piezas", {"diseno_reel": {**(pieza.get("diseno_reel") or {}), "cifras": cifras}},
                  id=f"eq.{pieza['id']}")
    return {"cifras": cifras}


def _fotos_reel(pieza: dict) -> list[int]:
    return list((pieza.get("diseno_reel") or {}).get("fotos") or [])


def foto_en_escena(pieza_id: int, escena: int, activa: bool) -> dict:
    """Activa o quita la foto con velo en una escena intermedia del reel sin cifra (si hay al menos dos; siempre
    queda un ícono). La imagen elegida antes para esa escena ya no aplica; si Krea está activo, se pide una nueva."""
    from rc import reels
    pieza = _pieza(int(pieza_id))
    escena = int(escena)
    if pieza["formato"] != "Reel" or not pieza.get("contenido"):
        raise ErrorNegocio("La foto en escenas es para reels con contenido.")
    sin = reels.escenas_sin_cifra(pieza["contenido"])
    if escena not in sin or len(sin) < 2:
        raise ErrorNegocio("Solo puede llevar foto una escena intermedia sin cifra, cuando hay al menos dos.")
    fotos = [n for n in _fotos_reel(pieza) if n != escena] + ([escena] if activa else [])
    validas = reels.fotos_validas(pieza["contenido"], fotos)
    if activa and escena not in validas:
        raise ErrorNegocio("Al menos una escena intermedia debe conservar su ícono.")
    db.actualizar("piezas", {"diseno_reel": {**(pieza.get("diseno_reel") or {}), "fotos": validas}},
                  id=f"eq.{pieza['id']}")
    db.actualizar("ilustraciones", {"elegida": False}, pieza_id=f"eq.{pieza['id']}", tarjeta=f"eq.{escena}",
                  elegida="is.true")
    if krea.configurado() and ajustes()["krea"].get("automaticas", True):
        try:
            generar_ilustraciones(pieza["id"], escena, cantidad=1, automatica=True)
        except Exception:  # noqa: BLE001 (la imagen es un extra)
            log.warning("No se pudo pedir la imagen de la escena %s", escena, exc_info=True)
    return {"fotos": validas}


def _tipos_imagen(pieza: dict) -> dict[int, str]:
    """{tarjeta o escena: tipo de imagen} que lleva la pieza (carrusel: 1 ícono, 2 foto, 3 línea; reel: 1 ícono
    isométrico animado y 2-4 ícono de línea si la escena no tiene cifra; el cierre nunca lleva imagen)."""
    from rc import reels, tarjetas
    if not pieza.get("contenido"):
        return {}
    if pieza["formato"] == "Reel":
        return reels.tipos_imagen(pieza["contenido"], _fotos_reel(pieza))
    return dict(tarjetas.TIPO_IMAGEN)


def _texto_imagen(pieza: dict, numero: int) -> dict:
    """Titular, texto y nota de la tarjeta o escena para describir su imagen."""
    from rc import reels
    if pieza["formato"] == "Reel":
        return {"titular": "", "texto": pieza["contenido"].get(reels.CAMPOS[numero - 1], ""), "nota": ""}
    return _texto_tarjeta(pieza["contenido"], numero)


def generar_ilustraciones(pieza_id: int, tarjeta: int, semilla: int = 0, descripcion: str | None = None,
                          cantidad: int | None = None, automatica: bool = False) -> dict:
    """Pide a Krea (Nano Banana Pro) varias variantes de la imagen de la tarjeta 1 (ícono isométrico en el estilo de
    la guía, con los íconos de la guía como referencia) o de la tarjeta 2 (foto realista).

    El tema sale, en este orden, de: la descripción que escribió el usuario, el `prompt_krea` de esa tarjeta o, si no
    hay, una descripción que Claude escribe a partir del texto de ESA tarjeta. Devuelve {"items": [...], "descripcion": str}.
    """
    from rc import estilo_iconos, tarjetas
    pieza = _pieza(int(pieza_id))
    tarjeta = int(tarjeta)
    tipos = _tipos_imagen(pieza)
    if not tipos:
        raise ErrorNegocio("Esta pieza aún no tiene contenido.")
    if tarjeta not in tipos:
        raise ErrorNegocio("Esa tarjeta o escena no lleva imagen (el cierre no lleva y las escenas con cifra la "
                           "muestran en grande).")
    if not krea.configurado():
        raise ErrorNegocio("Las imágenes no están activadas: falta KREA_API_TOKEN en Vercel (ver README).")
    tipo = tipos[tarjeta]
    k = ajustes()["krea"]
    foto_reel = tipo == "foto" and pieza["formato"] == "Reel"
    ancho, alto = (1376, 768) if tipo == "foto" and not foto_reel else (1024, 1024)
    contenido = pieza["contenido"]
    descripcion = " ".join((descripcion or "").split())[:500]
    if not descripcion and pieza["formato"] == "Carrusel":
        diseno = contenido.get("diseno") or []
        descripcion = (diseno[tarjeta - 1].get("prompt_krea") if len(diseno) >= tarjeta else "") or ""
    if not descripcion:
        t = _texto_imagen(pieza, tarjeta)
        try:
            descripcion = generador.describir_ilustracion(contenido.get("tema_especifico", ""), t["titular"],
                                                          t["texto"], t.get("nota", ""), tipo=tipo)
        except generador.ErrorGeneracion as e:
            raise ErrorNegocio(str(e)) from e
    fondo = tarjetas.color_de_tarjeta(tarjeta, tarjetas.inicio_de_semana(pieza.get("semana")))
    prompt = krea.construir_prompt(descripcion, tipo, fondo)
    referencias = (estilo_iconos.referencias_icono(env("APP_URL", False) or k.get("url_publica", ""), tipo)
                   if tipo in ("icono", "linea") else [])
    filas, fallo = [], None
    for _ in range(cantidad or k["variantes_por_clic"]):
        try:
            job_id = krea.crear_trabajo(prompt, "16:9" if tipo == "foto" and not foto_reel else "1:1", referencias)
        except ErrorNegocio as e:
            fallo = e
            break
        filas.append(db.insertar("ilustraciones", {
            "pieza_id": pieza["id"], "tarjeta": tarjeta, "job_id": job_id, "prompt": prompt,
            "descripcion": descripcion, "fondo": tarjetas.PALETA_2026[fondo],
            "ancho": ancho, "alto": alto, "automatica": automatica})[0])
    if fallo and not filas:
        raise fallo
    return {"items": filas, "descripcion": descripcion}


def sugerir_descripcion(pieza_id: int, tarjeta: int, previas: list[str] | None = None) -> dict:
    """Descripción sugerida en español de qué mostrar en la imagen de la tarjeta; con `previas`, una opción distinta."""
    pieza = _pieza(int(pieza_id))
    tarjeta = int(tarjeta)
    tipos = _tipos_imagen(pieza)
    if tarjeta not in tipos:
        raise ErrorNegocio("Esa tarjeta o escena no lleva imagen.")
    contenido = pieza["contenido"]
    t = _texto_imagen(pieza, tarjeta)
    try:
        descripcion = generador.describir_ilustracion(
            contenido.get("tema_especifico", ""), t["titular"], t["texto"], t.get("nota", ""),
            tipo=tipos[tarjeta], evitar=[str(p)[:500] for p in (previas or [])][:10])
    except generador.ErrorGeneracion as e:
        raise ErrorNegocio(str(e)) from e
    return {"descripcion": descripcion}


def imagenes_automaticas(pieza_id: int) -> int:
    """Al terminar los textos, pide a Krea una imagen por tarjeta o escena que la lleve (ver `_tipos_imagen`); la primera
    que queda lista se usa (y en la escena 1 del reel, se anima: ver `ilustraciones`). Nunca hace fallar la generación
    de textos: si Krea no está configurado o falla, la pieza queda con los espacios para generar a mano."""
    pieza = _pieza(int(pieza_id))
    if not pieza.get("contenido") or not krea.configurado():
        return 0
    if not ajustes()["krea"].get("automaticas", True):
        return 0
    pedidas = 0
    for tarjeta in _tipos_imagen(pieza):
        try:
            pedidas += len(generar_ilustraciones(pieza["id"], tarjeta, cantidad=1, automatica=True)["items"])
        except Exception:  # noqa: BLE001 (las imágenes son un extra: no deben romper la entrega de textos)
            log.warning("No se pudo pedir la imagen automática de la tarjeta %s de la pieza %s", tarjeta, pieza["id"],
                        exc_info=True)
    return pedidas


def detener_ilustraciones(pieza_id: int, tarjeta: int) -> dict:
    """Cancela en Krea las variantes en cola de esa tarjeta (Krea no cobra los trabajos cancelados)."""
    filas = db.seleccionar("ilustraciones", select="id,job_id", pieza_id=f"eq.{int(pieza_id)}",
                           tarjeta=f"eq.{int(tarjeta)}", estado="eq.en_cola")
    for f in filas:
        try:
            krea.cancelar(f["job_id"])
        except ErrorNegocio:
            log.warning("Krea no canceló el trabajo %s (quizá ya había terminado)", f["job_id"])
        db.actualizar("ilustraciones", {"estado": "fallida", "error": "Detenida por el usuario."},
                      id=f"eq.{f['id']}", estado="eq.en_cola")
    videos = db.seleccionar("ilustraciones", select="id,video_job_id", pieza_id=f"eq.{int(pieza_id)}",
                            tarjeta=f"eq.{int(tarjeta)}", video_estado="eq.en_cola")
    for f in videos:
        try:
            krea.cancelar(f["video_job_id"])
        except ErrorNegocio:
            log.warning("Krea no canceló el video %s", f["video_job_id"])
        db.actualizar("ilustraciones", {"video_estado": "fallida", "video_error": "Detenido por el usuario."},
                      id=f"eq.{f['id']}", video_estado="eq.en_cola")
    return {"detenidas": len(filas) + len(videos)}


def borrar_ilustraciones(pieza_id: int, tarjeta: int, ilustracion_id: int | None = None,
                         solo_animacion: bool = False) -> dict:
    """Borra de la base de datos las imágenes (o solo sus animaciones) que NO están en uso en la tarjeta o escena.

    Sin `ilustracion_id`: todas las no elegidas de esa tarjeta. Las que siguen en cola se cancelan en Krea. La elegida
    nunca se borra. Los archivos viven en Krea: aquí solo se quita el registro (y deja de ocupar espacio en Supabase).
    """
    filtros = {"pieza_id": f"eq.{int(pieza_id)}", "tarjeta": f"eq.{int(tarjeta)}", "elegida": "is.false"}
    if ilustracion_id is not None:
        filtros["id"] = f"eq.{int(ilustracion_id)}"
    filas = db.seleccionar("ilustraciones", select="id,job_id,estado,video_job_id,video_estado", **filtros)
    if ilustracion_id is not None and not filas:
        raise ErrorNegocio("No se puede borrar: la imagen está en uso o ya no existe.")
    for f in filas:
        for job, estado in ((f.get("video_job_id"), f.get("video_estado")),
                            (None if solo_animacion else f["job_id"], f["estado"])):
            if job and estado == "en_cola":
                try:
                    krea.cancelar(job)
                except ErrorNegocio:
                    log.warning("Krea no canceló el trabajo %s", job)
    ids = ",".join(str(f["id"]) for f in filas)
    if ids:
        if solo_animacion:
            db.actualizar("ilustraciones", {"video_job_id": None, "video_estado": None, "video_url": None,
                                            "video_error": None, "video_pedido_en": None}, id=f"in.({ids})")
        else:
            db.borrar("ilustraciones", id=f"in.({ids})")
    return {"borradas": len(filas)}


def elegir_ilustracion(ilustracion_id: int, elegida: bool = True) -> dict:
    """Marca una variante lista como la que se monta en su tarjeta (solo una por tarjeta), o la quita."""
    filas = db.seleccionar("ilustraciones", select="*", id=f"eq.{int(ilustracion_id)}")
    if not filas:
        raise ErrorNegocio("La ilustración no existe.")
    fila = filas[0]
    if elegida and (fila["estado"] != "lista" or not str(fila.get("url") or "").startswith("https://")):
        raise ErrorNegocio("Solo se puede usar una ilustración que ya terminó de generarse.")
    db.actualizar("ilustraciones", {"elegida": False}, pieza_id=f"eq.{fila['pieza_id']}",
                  tarjeta=f"eq.{fila['tarjeta']}", elegida="is.true")
    if elegida:
        db.actualizar("ilustraciones", {"elegida": True}, id=f"eq.{fila['id']}")
    return {**fila, "elegida": bool(elegida)}


MAX_BYTES_ILUSTRACION = 15 * 1024 * 1024


def _imagenes_elegidas(pieza_id: int) -> dict[int, bytes]:
    """{tarjeta: bytes} de las ilustraciones elegidas, descargadas de Krea. Si una falla, esa tarjeta queda sin imagen."""
    import urllib.request
    if krea.configurado():
        ilustraciones(pieza_id)  # actualiza las que siguen en cola (y elige las automáticas que ya están listas)
    imagenes = {}
    for f in db.seleccionar("ilustraciones", select="tarjeta,url", pieza_id=f"eq.{int(pieza_id)}", elegida="is.true"):
        url = str(f.get("url") or "")
        if not url.startswith("https://"):
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "contenidos-rc"}), timeout=20) as r:
                datos = r.read(MAX_BYTES_ILUSTRACION + 1)
            if len(datos) <= MAX_BYTES_ILUSTRACION:
                imagenes[int(f["tarjeta"])] = datos
        except Exception:
            log.warning("No se pudo descargar la ilustración elegida de la tarjeta %s", f["tarjeta"], exc_info=True)
    return imagenes


MINUTOS_MAX_VIDEO = 20


def animar_ilustracion(ilustracion_id: int) -> dict:
    """Pide a Krea el video corto (ícono isométrico animado, en bucle) de una imagen lista de la escena 1 de un reel."""
    filas = db.seleccionar("ilustraciones", select="*", id=f"eq.{int(ilustracion_id)}")
    if not filas:
        raise ErrorNegocio("La imagen no existe.")
    fila = filas[0]
    pieza = _pieza(fila["pieza_id"])
    if pieza["formato"] != "Reel" or int(fila["tarjeta"]) != 1:
        raise ErrorNegocio("Solo se anima el ícono isométrico de la escena 1 de los reels.")
    if fila["estado"] != "lista" or not str(fila.get("url") or "").startswith("https://"):
        raise ErrorNegocio("Solo se puede animar una imagen que ya terminó de generarse.")
    if fila.get("video_estado") == "en_cola":
        raise ErrorNegocio("Este ícono ya se está animando.")
    job_id = krea.crear_video(fila["url"], fila.get("fondo") or "")
    cambios = {"video_job_id": job_id, "video_estado": "en_cola", "video_url": None, "video_error": None,
               "video_pedido_en": _ahora()}
    db.actualizar("ilustraciones", cambios, id=f"eq.{fila['id']}")
    return {**fila, **cambios}


def ilustraciones(pieza_id: int) -> dict:
    """Variantes de la pieza (más recientes primero); actualiza las que siguen en cola (imágenes y videos) consultando
    a Krea. Las automáticas que quedan listas se eligen solas y, en la escena 1 de un reel, se animan."""
    filas = db.seleccionar("ilustraciones", select="*", pieza_id=f"eq.{int(pieza_id)}", order="id.desc", limit="30")
    ahora = datetime.now(timezone.utc)
    limite = (ahora - timedelta(minutes=MINUTOS_MAX_ILUSTRACION)).isoformat()
    for f in filas:
        if f["estado"] == "en_cola":
            try:
                nuevo = krea.consultar(f["job_id"])
            except ErrorNegocio:
                continue  # error transitorio al consultar: se reintenta en la siguiente consulta
            if nuevo["estado"] == "en_cola" and f["creado_en"] < limite:
                nuevo = {"estado": "fallida", "url": None, "error": "Krea tardó demasiado en responder."}
            if nuevo["estado"] != "en_cola":
                db.actualizar("ilustraciones", nuevo, id=f"eq.{f['id']}", estado="eq.en_cola")
                f.update(nuevo)
                # Imagen automática lista y la tarjeta aún sin imagen elegida: se usa directamente.
                if f.get("automatica") and nuevo["estado"] == "lista" and not any(
                        o.get("elegida") and o["tarjeta"] == f["tarjeta"] for o in filas):
                    db.actualizar("ilustraciones", {"elegida": True}, id=f"eq.{f['id']}")
                    f["elegida"] = True
                    if int(f["tarjeta"]) == 1 and _pieza(f["pieza_id"])["formato"] == "Reel":
                        try:
                            f.update(animar_ilustracion(f["id"]))
                        except ErrorNegocio:
                            log.warning("No se pudo animar el ícono %s", f["id"], exc_info=True)
        if f.get("video_estado") == "en_cola" and f.get("video_job_id"):
            try:
                video = krea.consultar(f["video_job_id"])
            except ErrorNegocio:
                continue
            pedido = f.get("video_pedido_en") or f["creado_en"]  # el tiempo se mide desde que se pidió el video
            if video["estado"] == "en_cola" and pedido < (ahora - timedelta(minutes=MINUTOS_MAX_VIDEO)).isoformat():
                video = {"estado": "fallida", "url": None, "error": "Krea tardó demasiado en animar el ícono."}
            if video["estado"] != "en_cola":
                cambios = {"video_estado": video["estado"], "video_url": video["url"], "video_error": video["error"]}
                db.actualizar("ilustraciones", cambios, id=f"eq.{f['id']}", video_estado="eq.en_cola")
                f.update(cambios)
    return {"configurado": krea.configurado(), "items": filas}


def repositorio() -> list[dict]:
    """Piezas con contenido de meses aprobados, entregados o históricos (más recientes primero)."""
    filas = db.seleccionar(
        "piezas",
        select="id,semana,fecha_publicacion,formato,tipo,pilar,estado,version,contenido,aprobada_en,creado_en,"
               "aprobaciones,meses!inner(mes_objetivo,estado,aprobado_en)",
        contenido="not.is.null", **{"meses.estado": "in.(aprobado,entregado,historico)"})
    resultado = []
    for f in filas:
        m = f.pop("meses") or {}
        contenido = f.get("contenido") or {}
        historico = m.get("estado") == "historico"
        resultado.append({
            **f,
            "mes_objetivo": None if historico else m.get("mes_objetivo"),
            "estado_mes": m.get("estado"),
            "mes_aprobado_en": m.get("aprobado_en"),
            # Lista para publicar = aprobación final de Luís («entregado» queda solo en meses antiguos).
            "publicada_en": ((f.get("aprobaciones") or {}).get("publicacion") or {}).get("en"),
            "historico": historico,
            "tema": contenido.get("tema_especifico", ""),
            "tendencia": (contenido.get("investigacion") or {}).get("tendencia", ""),
        })
    resultado.sort(key=lambda r: (r["mes_objetivo"] or "", r["semana"]), reverse=True)
    return resultado


def versiones(pieza_id: int) -> list[dict]:
    return db.seleccionar("versiones_pieza", select="version,motivo,contenido,creado_en",
                          pieza_id=f"eq.{int(pieza_id)}", order="version.desc")


def borrar_piezas(ids: list[int]) -> int:
    """Borra piezas del repositorio (con sus versiones y comentarios). Solo de meses ya aprobados,
    entregados o históricos; si un mes se queda sin piezas, también se borra el mes."""
    ids = sorted({int(i) for i in ids})
    if not ids:
        raise ErrorNegocio("No hay nada seleccionado.")
    lista = ",".join(str(i) for i in ids)
    filas = db.seleccionar("piezas", select="id,mes_id,meses!inner(estado)", id=f"in.({lista})",
                           **{"meses.estado": "in.(aprobado,entregado,historico)"})
    if len(filas) != len(ids):
        raise ErrorNegocio("Solo se pueden borrar contenidos del repositorio (meses aprobados, entregados o históricos).")
    db.borrar("piezas", id=f"in.({lista})")
    for mes_id in {f["mes_id"] for f in filas}:
        if not db.seleccionar("piezas", select="id", mes_id=f"eq.{mes_id}", limit="1"):
            db.borrar("meses", id=f"eq.{mes_id}")
    return len(ids)
