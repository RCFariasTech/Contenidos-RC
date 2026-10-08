"""Lógica de negocio de la sección "Propuestas del próximo mes" (PLAN.md, sección 5)."""

import logging
from datetime import date, datetime, timedelta, timezone

from rc import correos, db, fuentes, generador, krea, planificador, teams, validador
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
        return fila
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
        return fila
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


# ---------- exportación ----------

def _construir_pptx(mes: date) -> tuple[dict, list[dict], str, bytes]:
    from rc import pptx_export  # import diferido: python-pptx solo se carga al exportar
    fila_mes = obtener_mes(mes)
    if not fila_mes:
        raise ErrorNegocio("Ese mes no tiene propuestas.")
    if fila_mes["estado"] not in ("aprobado", "entregado"):
        raise ErrorNegocio("El PowerPoint se habilita cuando las 4 piezas están aprobadas.")
    piezas = db.seleccionar("piezas", select="*", mes_id=f"eq.{fila_mes['id']}", order="semana")
    contenido = pptx_export.generar_pptx(fila_mes["mes_objetivo"], piezas, fila_mes.get("aprobado_en"))
    return fila_mes, piezas, pptx_export.nombre_archivo(fila_mes["mes_objetivo"]), contenido


def _marcar_entregado(fila_mes: dict) -> None:
    if fila_mes["estado"] == "aprobado":
        db.actualizar("meses", {"estado": "entregado", "entregado_en": _ahora()},
                      id=f"eq.{fila_mes['id']}", estado="eq.aprobado")


def exportar_pptx(mes: date) -> tuple[str, bytes]:
    """PowerPoint del mes aprobado. La primera descarga marca el mes como entregado."""
    fila_mes, _piezas, nombre, contenido = _construir_pptx(mes)
    _marcar_entregado(fila_mes)
    return nombre, contenido


def _variante(pieza: dict) -> tuple[str, int]:
    """(mes_objetivo, variante): cambia de una pieza a otra y de un mes a otro, así los colores del feed rotan."""
    mes = db.seleccionar("meses", select="mes_objetivo", id=f"eq.{pieza['mes_id']}")[0]["mes_objetivo"]
    mismas = db.seleccionar("piezas", select="id", mes_id=f"eq.{pieza['mes_id']}",
                            formato=f"eq.{pieza['formato']}", order="semana")
    return mes, int(mes[5:7]) * 2 + [c["id"] for c in mismas].index(pieza["id"])


def tarjetas_pdf(pieza_id: int, semilla: int = 0, guias: bool = False) -> tuple[str, bytes]:
    """PDF para diseño: las 5 tarjetas 3:4 de un carrusel o el guion visual 9:16 de un reel."""
    from rc import reels, tarjetas  # import diferido: reportlab/svglib solo se cargan al generar
    pieza = _pieza(pieza_id)
    if not pieza.get("contenido"):
        raise ErrorNegocio("Esta pieza aún no tiene contenido.")
    mes, variante = _variante(pieza)
    contenido = pieza["contenido"]
    modulo, rotulo = (reels, "Reel") if pieza["formato"] == "Reel" else (tarjetas, "Carrusel")
    extra = {"imagenes": _imagenes_elegidas(pieza["id"])} if modulo is tarjetas else {}
    pdf = modulo.generar_pdf(contenido, f"{rotulo} · {contenido.get('tema_especifico', '')}", variante,
                             semilla=max(0, int(semilla)), guias=guias, **extra)
    return modulo.nombre_archivo(contenido, mes), pdf


def vista_tarjetas(pieza_id: int, semilla: int = 0, ancho: int = 720) -> dict:
    """Las páginas como imágenes PNG (data URI) para la vista previa tipo carrusel, y su relación de aspecto."""
    import base64
    from rc import tarjetas
    pieza = _pieza(pieza_id)
    _nombre, pdf = tarjetas_pdf(pieza_id, semilla, guias=True)
    imagenes = ["data:image/png;base64," + base64.b64encode(png).decode() for png in tarjetas.imagenes_png(pdf, max(200, min(int(ancho), 900)))]
    return {"imagenes": imagenes, "relacion": 9 / 16 if pieza["formato"] == "Reel" else 3 / 4}


# ---------- ilustraciones 3D (Krea) ----------

MINUTOS_MAX_ILUSTRACION = 10


def _texto_tarjeta(contenido: dict, tarjeta: int) -> dict:
    """Titular, texto y nota de la tarjeta (usa `diseno` o, en contenidos viejos, la división automática)."""
    from rc import tarjetas
    return tarjetas.datos_tarjetas(contenido)[tarjeta - 1]


def generar_ilustraciones(pieza_id: int, tarjeta: int, semilla: int = 0, descripcion: str | None = None) -> dict:
    """Pide a Krea varias variantes de la ilustración de la tarjeta 1 o 2 (LoRA «3d characters Flux»).

    La escena sale, en este orden, de: la descripción que escribió el usuario, el `prompt_krea` de esa tarjeta o,
    si no hay, una descripción que Claude escribe a partir del texto de ESA tarjeta (para que cada ilustración
    corresponda a su tarjeta). Devuelve {"items": [...], "descripcion": str}.
    """
    from rc import tarjetas
    pieza = _pieza(int(pieza_id))
    tarjeta = int(tarjeta)
    if pieza["formato"] != "Carrusel" or not pieza.get("contenido"):
        raise ErrorNegocio("Las ilustraciones son para tarjetas de carruseles con contenido.")
    if tarjeta not in (1, 2):
        raise ErrorNegocio("Solo las tarjetas 1 y 2 llevan ilustración.")
    if not krea.configurado():
        raise ErrorNegocio("Las ilustraciones no están activadas: falta KREA_API_TOKEN en Vercel (ver README).")
    _mes, variante = _variante(pieza)
    semilla = max(0, int(semilla))
    estilo = tarjetas.estilo_de_tarjeta(tarjeta, variante, semilla)
    clave, hex_fondo = tarjetas.fondo_de_tarjeta(tarjeta, variante, semilla)
    k = ajustes()["krea"]
    ancho, alto = tarjetas.tamano_ilustracion(estilo, k["lado_largo"])
    contenido = pieza["contenido"]
    descripcion = " ".join((descripcion or "").split())[:500]
    if not descripcion:
        diseno = contenido.get("diseno") or []
        descripcion = (diseno[tarjeta - 1].get("prompt_krea") if len(diseno) >= tarjeta else "") or ""
    if not descripcion:
        t = _texto_tarjeta(contenido, tarjeta)
        try:
            descripcion = generador.describir_ilustracion(contenido.get("tema_especifico", ""), t["titular"],
                                                          t["texto"], t.get("nota", ""))
        except generador.ErrorGeneracion as e:
            raise ErrorNegocio(str(e)) from e
    prompt = krea.construir_prompt(descripcion, clave, hex_fondo, tarjetas.COMPOSICION.get(estilo, ""))
    base = (env("APP_URL", False) or teams.APP_URL_POR_DEFECTO).rstrip("/")
    guia = f"{base}/api/guia-composicion?estilo={estilo}&color={hex_fondo.lstrip('#')}&w={ancho}&h={alto}"
    filas, fallo = [], None
    for _ in range(k["variantes_por_clic"]):
        try:
            job_id = krea.crear_trabajo(prompt, ancho, alto, guia)
        except ErrorNegocio as e:
            fallo = e
            break
        filas.append(db.insertar("ilustraciones", {
            "pieza_id": pieza["id"], "tarjeta": tarjeta, "job_id": job_id, "prompt": prompt,
            "descripcion": descripcion, "fondo": hex_fondo, "ancho": ancho, "alto": alto})[0])
    if fallo and not filas:
        raise fallo
    return {"items": filas, "descripcion": descripcion}


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


def ilustraciones(pieza_id: int) -> dict:
    """Variantes de la pieza (más recientes primero); actualiza las que siguen en cola consultando a Krea."""
    filas = db.seleccionar("ilustraciones", select="*", pieza_id=f"eq.{int(pieza_id)}", order="id.desc", limit="30")
    limite = (datetime.now(timezone.utc) - timedelta(minutes=MINUTOS_MAX_ILUSTRACION)).isoformat()
    for f in filas:
        if f["estado"] != "en_cola":
            continue
        try:
            nuevo = krea.consultar(f["job_id"])
        except ErrorNegocio:
            continue  # error transitorio al consultar: se reintenta en la siguiente consulta
        if nuevo["estado"] == "en_cola" and f["creado_en"] < limite:
            nuevo = {"estado": "fallida", "url": None, "error": "Krea tardó demasiado en responder."}
        if nuevo["estado"] != "en_cola":
            db.actualizar("ilustraciones", nuevo, id=f"eq.{f['id']}", estado="eq.en_cola")
            f.update(nuevo)
    return {"configurado": krea.configurado(), "items": filas}


def enviar_pptx(mes: date, destinatarios: list[str], mensaje: str = "", guardar_favoritos: bool = False) -> list[str]:
    """Envía el PowerPoint por correo; marca el mes como entregado solo si el envío salió bien."""
    from rc import pptx_export
    emails = list(dict.fromkeys(correos.validar_email(e) for e in destinatarios))
    fila_mes, piezas, nombre, contenido = _construir_pptx(mes)
    mes_texto = pptx_export.nombre_mes(fila_mes["mes_objetivo"])
    lineas = [f"- Semana {p['semana']} · {p['formato']} · {pptx_export.fecha_larga(p.get('fecha_publicacion'))}: "
              f"{(p.get('contenido') or {}).get('tema_especifico', '')}" for p in piezas]
    cuerpo = (f"Hola,\n\nAdjunto el PowerPoint con el contenido de Instagram de {mes_texto}.\n\n"
              + (f"{mensaje.strip()}\n\n" if mensaje.strip() else "")
              + "Piezas incluidas:\n" + "\n".join(lineas)
              + "\n\nCada slide trae formato, medidas, textos por tarjeta o escena, caption, hashtags y fuente.\n\n"
              "RC Farías · Experiencias de marca")
    correos.enviar(emails, f"Contenido Instagram RC Farías · {mes_texto}", cuerpo, contenido, nombre)
    _marcar_entregado(fila_mes)
    if guardar_favoritos:
        existentes = {f["email"] for f in correos.listar_favoritos()}
        for e in emails:
            if e not in existentes:
                correos.agregar_favorito(e)
    return emails


# ---------- repositorio ----------

def repositorio() -> list[dict]:
    """Piezas con contenido de meses aprobados, entregados o históricos (más recientes primero)."""
    filas = db.seleccionar(
        "piezas",
        select="id,semana,fecha_publicacion,formato,tipo,pilar,estado,version,contenido,aprobada_en,creado_en,"
               "meses!inner(mes_objetivo,estado,aprobado_en,entregado_en)",
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
            "mes_entregado_en": m.get("entregado_en"),
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
