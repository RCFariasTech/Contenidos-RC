"""Única función serverless de la app (Vercel, runtime Python).

vercel.json reescribe /api/<ruta> → /api/index?ruta=<ruta>. Este archivo solo enruta;
la lógica vive en el paquete rc/.
"""

import json
import logging
import sys
import time
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rc import auth, db  # noqa: E402
from rc.config import env  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

MAX_CUERPO = 64 * 1024
PRESUPUESTO_CRON_S = 100  # el cron solo arranca otra pieza si lleva menos de esto (maxDuration = 300)


class Archivo:
    """Respuesta binaria (descarga) en lugar de JSON."""

    def __init__(self, nombre: str, contenido: bytes, tipo: str):
        self.nombre, self.contenido, self.tipo = nombre, contenido, tipo


class ErrorCliente(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado


# ---------- rutas ----------

def ruta_config(_req):
    # Valores públicos por diseño: el login del frontend los necesita.
    return 200, {"supabase_url": env("SUPABASE_URL"), "supabase_anon_key": env("SUPABASE_ANON_KEY")}


def ruta_salud(_req):
    return 200, {"ok": True}


def _dueno(req) -> dict:
    return auth.usuario_desde_token(req["authorization"])


def _servicio():
    from rc import servicio  # import diferido: carga el SDK de Anthropic solo cuando hace falta
    return servicio


def _mes_param(valor: str | None):
    from rc import planificador
    if not valor:
        return planificador.mes_siguiente(planificador.hoy_bogota())
    try:
        anio, mes = (int(x) for x in valor.split("-")[:2])
        return date(anio, mes, 1)
    except ValueError as e:
        raise ErrorCliente(400, "mes debe tener formato AAAA-MM") from e


def _entero(cuerpo: dict, campo: str) -> int:
    try:
        return int(cuerpo[campo])
    except (KeyError, TypeError, ValueError) as e:
        raise ErrorCliente(400, f"Falta o es inválido: {campo}") from e


def ruta_yo(req):
    usuario = _dueno(req)
    return 200, {"email": usuario.get("email")}


def ruta_mes_actual(req):
    _dueno(req)
    return 200, _servicio().estado_mes(_mes_param(req["query"].get("mes")))


def ruta_iniciar_mes(req):
    _dueno(req)
    s = _servicio()
    mes = _mes_param(req["cuerpo"].get("mes"))
    s.iniciar_mes(mes)
    return 200, s.estado_mes(mes)


def ruta_generar_pieza(req):
    _dueno(req)
    return 200, _servicio().generar_pieza(_entero(req["cuerpo"], "pieza_id"))


def ruta_ajustar_pieza(req):
    _dueno(req)
    return 200, _servicio().ajustar_pieza(_entero(req["cuerpo"], "pieza_id"))


def ruta_rehacer_pieza(req):
    _dueno(req)
    return 200, _servicio().rehacer_pieza(_entero(req["cuerpo"], "pieza_id"))


def ruta_comentar(req):
    _dueno(req)
    return 200, _servicio().comentar(_entero(req["cuerpo"], "pieza_id"), req["cuerpo"].get("texto"))


def ruta_borrar_comentario(req):
    _dueno(req)
    _servicio().borrar_comentario(_entero(req["query"], "id"))
    return 200, {"ok": True}


def ruta_aprobar(req):
    _dueno(req)
    return 200, _servicio().aprobar(_entero(req["cuerpo"], "pieza_id"), bool(req["cuerpo"].get("aprobada")))


def ruta_fecha(req):
    _dueno(req)
    return 200, _servicio().cambiar_fecha(_entero(req["cuerpo"], "pieza_id"), req["cuerpo"].get("fecha"))


def ruta_repositorio(req):
    _dueno(req)
    return 200, {"piezas": _servicio().repositorio()}


def ruta_versiones(req):
    _dueno(req)
    return 200, {"versiones": _servicio().versiones(_entero(req["query"], "pieza_id"))}


def ruta_configuracion(req):
    _dueno(req)
    from rc import correos, fuentes, teams
    return 200, {"fuentes": fuentes.listar(), "recomendadas": fuentes.recomendadas(),
                 "favoritos": correos.listar_favoritos(), "correo_configurado": correos.configurado(),
                 "teams_configurado": teams.configurado()}


def ruta_fuente_agregar(req):
    _dueno(req)
    from rc import fuentes
    return 200, {"dominio": fuentes.agregar(req["cuerpo"].get("dominio", ""))}


def ruta_fuente_quitar(req):
    _dueno(req)
    from rc import fuentes
    fuentes.quitar(req["query"].get("dominio", ""))
    return 200, {"ok": True}


def ruta_fuentes_restaurar(req):
    _dueno(req)
    from rc import fuentes
    return 200, {"agregadas": fuentes.restaurar()}


def ruta_favorito_agregar(req):
    _dueno(req)
    from rc import correos
    return 200, correos.agregar_favorito(req["cuerpo"].get("email", ""), req["cuerpo"].get("nombre"))


def ruta_favorito_borrar(req):
    _dueno(req)
    from rc import correos
    correos.borrar_favorito(_entero(req["query"], "id"))
    return 200, {"ok": True}


def ruta_borrar_piezas(req):
    _dueno(req)
    ids = req["cuerpo"].get("ids")
    if not isinstance(ids, list) or len(ids) > 100:
        raise ErrorCliente(400, "ids debe ser una lista de hasta 100 piezas")
    try:
        return 200, {"borradas": _servicio().borrar_piezas([int(i) for i in ids])}
    except (TypeError, ValueError) as e:
        raise ErrorCliente(400, "ids inválidos") from e


def ruta_enviar_pptx(req):
    _dueno(req)
    from rc import correos
    cuerpo = req["cuerpo"]
    destinatarios = [*(cuerpo.get("favoritos") or []), *correos.separar_correos(cuerpo.get("otros", ""))]
    enviados = _servicio().enviar_pptx(_mes_param(cuerpo.get("mes")), destinatarios,
                                       str(cuerpo.get("mensaje") or "")[:1000],
                                       bool(cuerpo.get("guardar_favoritos")))
    return 200, {"enviados": enviados}


def ruta_exportar_pptx(req):
    _dueno(req)
    nombre, contenido = _servicio().exportar_pptx(_mes_param(req["query"].get("mes")))
    return 200, Archivo(nombre, contenido,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")


def _semilla(req) -> int:
    """Número de «Rehacer» (0 = propuesta inicial); acotado para que no se use como vector de abuso."""
    try:
        return max(0, min(int(req["query"].get("semilla", "0")), 1000))
    except ValueError:
        return 0


def ruta_tarjetas_pdf(req):
    _dueno(req)
    try:
        pieza_id = int(req["query"].get("pieza", ""))
    except ValueError:
        raise ErrorCliente(400, "Falta la pieza.")
    nombre, contenido = _servicio().tarjetas_pdf(pieza_id, _semilla(req))
    return 200, Archivo(nombre, contenido, "application/pdf")


def ruta_tarjetas_vista(req):
    _dueno(req)
    try:
        pieza_id = int(req["query"].get("pieza", ""))
    except ValueError:
        raise ErrorCliente(400, "Falta la pieza.")
    try:
        ancho = int(req["query"].get("ancho", "720"))
    except ValueError:
        ancho = 720
    return 200, _servicio().vista_tarjetas(pieza_id, _semilla(req), ancho)


def ruta_ilustraciones_listar(req):
    _dueno(req)
    try:
        pieza_id = int(req["query"].get("pieza", ""))
    except ValueError:
        raise ErrorCliente(400, "Falta la pieza.")
    return 200, _servicio().ilustraciones(pieza_id)


def ruta_ilustraciones_generar(req):
    _dueno(req)
    cuerpo = req["cuerpo"]
    return 200, _servicio().generar_ilustraciones(_entero(cuerpo, "pieza_id"), _entero(cuerpo, "tarjeta"),
                                                  int(cuerpo.get("semilla") or 0),
                                                  str(cuerpo.get("descripcion") or "")[:500])


def ruta_ilustracion_elegir(req):
    _dueno(req)
    cuerpo = req["cuerpo"]
    return 200, _servicio().elegir_ilustracion(_entero(cuerpo, "id"), bool(cuerpo.get("elegida", True)))


def ruta_verificar_conexiones(req):
    """Estado de las claves e integraciones, sin generar contenido."""
    _dueno(req)
    from rc import correos, generador, krea, teams
    return 200, {
        "anthropic": generador.verificar_clave(),
        "krea": {"ok": krea.configurado(), "detalle": "Clave configurada." if krea.configurado() else "Falta KREA_API_TOKEN."},
        "correo": {"ok": correos.configurado(), "detalle": "SMTP configurado." if correos.configurado() else "Faltan SMTP_USER y SMTP_PASSWORD."},
        "teams": {"ok": teams.configurado(), "detalle": "Webhook configurado." if teams.configurado() else "Falta TEAMS_WEBHOOK_URL."},
    }


def ruta_probar_teams(req):
    _dueno(req)
    from rc import teams
    teams.enviar_prueba()
    return 200, {"ok": True}


def ruta_diario(req):
    """Cron diario: mantiene activo Supabase y, desde el día 15, prepara y genera el mes siguiente."""
    if not auth.es_cron_valido(req["authorization"]):
        raise ErrorCliente(401, "No autorizado")
    from rc import planificador
    from rc.config import ajustes
    inicio = time.monotonic()
    hoy = planificador.hoy_bogota()
    if hoy.day < ajustes()["dia_inicio_generacion"]:
        db.seleccionar("meses", select="id", limit="1")
        return 200, {"ok": True, "accion": "latido"}
    s = _servicio()
    mes = planificador.mes_siguiente(hoy)
    s.iniciar_mes(mes)
    generadas = []
    for pieza in s.estado_mes(mes)["piezas"]:
        if pieza["estado"] not in ("pendiente", "error"):
            continue
        if time.monotonic() - inicio > PRESUPUESTO_CRON_S:
            break  # el resto se completa al día siguiente o al abrir la app
        try:
            s.generar_pieza(pieza["id"])
            generadas.append(pieza["id"])
        except Exception:  # noqa: BLE001 (queda en estado "error"; se reintenta luego)
            log.exception("El cron no pudo generar la pieza %s", pieza["id"])
    return 200, {"ok": True, "accion": "generacion", "generadas": generadas}


def ruta_diagnostico(req):
    """Prueba aislada de generación (no guarda nada). Acceso: CRON_SECRET o la sesión del dueño."""
    if not auth.es_cron_valido(req["authorization"]):
        _dueno(req)
    from rc import generador
    formato = req["query"].get("formato", "Carrusel")
    if formato not in ("Carrusel", "Reel"):
        raise ErrorCliente(400, "formato debe ser Carrusel o Reel")
    slot = {"semana": 1, "formato": formato, "tipo": "Tendencia", "pilar": "Tendencias de marketing BTL"}
    return 200, generador.generar(slot, historial=[], hermanas=[])


RUTAS = {
    ("GET", "config"): ruta_config,
    ("GET", "salud"): ruta_salud,
    ("GET", "yo"): ruta_yo,
    ("GET", "mes-actual"): ruta_mes_actual,
    ("POST", "iniciar-mes"): ruta_iniciar_mes,
    ("POST", "generar-pieza"): ruta_generar_pieza,
    ("POST", "ajustar-pieza"): ruta_ajustar_pieza,
    ("POST", "rehacer-pieza"): ruta_rehacer_pieza,
    ("POST", "comentarios"): ruta_comentar,
    ("DELETE", "comentarios"): ruta_borrar_comentario,
    ("POST", "aprobar"): ruta_aprobar,
    ("POST", "fecha"): ruta_fecha,
    ("GET", "exportar-pptx"): ruta_exportar_pptx,
    ("GET", "tarjetas-pdf"): ruta_tarjetas_pdf,
    ("GET", "tarjetas-vista"): ruta_tarjetas_vista,
    ("GET", "configuracion"): ruta_configuracion,
    ("POST", "probar-teams"): ruta_probar_teams,
    ("GET", "verificar-conexiones"): ruta_verificar_conexiones,
    ("GET", "ilustraciones"): ruta_ilustraciones_listar,
    ("POST", "ilustraciones"): ruta_ilustraciones_generar,
    ("POST", "ilustracion-elegir"): ruta_ilustracion_elegir,
    ("POST", "fuentes"): ruta_fuente_agregar,
    ("DELETE", "fuentes"): ruta_fuente_quitar,
    ("POST", "fuentes-restaurar"): ruta_fuentes_restaurar,
    ("POST", "favoritos"): ruta_favorito_agregar,
    ("DELETE", "favoritos"): ruta_favorito_borrar,
    ("POST", "borrar-piezas"): ruta_borrar_piezas,
    ("POST", "enviar-pptx"): ruta_enviar_pptx,
    ("GET", "repositorio"): ruta_repositorio,
    ("GET", "versiones"): ruta_versiones,
    ("GET", "diario"): ruta_diario,
    ("GET", "diagnostico"): ruta_diagnostico,
}


# ---------- infraestructura HTTP ----------

def _error_conocido(e: Exception):
    """Errores esperables con mensaje para el usuario; None si es un error inesperado."""
    if isinstance(e, json.JSONDecodeError):
        return 400, {"error": "JSON inválido"}
    nombre = type(e).__name__
    if nombre == "ErrorNegocio":
        return 409, {"error": str(e)}
    if nombre == "ErrorGeneracion":
        return 502, {"error": f"No se pudo generar con Claude: {e}"}
    return None


class handler(BaseHTTPRequestHandler):  # noqa: N801 (nombre exigido por Vercel)

    def _atender(self, metodo: str):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        ruta = query.pop("ruta", None) or url.path.removeprefix("/api/").strip("/")
        try:
            funcion = RUTAS.get((metodo, ruta))
            if funcion is None:
                raise ErrorCliente(404, "Ruta no encontrada")
            longitud = int(self.headers.get("Content-Length") or 0)
            if longitud > MAX_CUERPO:
                raise ErrorCliente(413, "Cuerpo demasiado grande")
            cuerpo = json.loads(self.rfile.read(longitud) or b"{}") if longitud else {}
            req = {"query": query, "cuerpo": cuerpo,
                   "authorization": self.headers.get("Authorization")}
            estado, datos = funcion(req)
        except ErrorCliente as e:
            estado, datos = e.estado, {"error": str(e)}
        except auth.NoAutorizado as e:
            estado, datos = 401, {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            estado, datos = _error_conocido(e) or (None, None)
            if estado is None:
                log.error("Error en /api/%s: %s\n%s", ruta, e, traceback.format_exc())
                estado, datos = 500, {"error": f"{type(e).__name__}: {e}"}
        if isinstance(datos, Archivo):
            self._responder_archivo(datos)
        else:
            self._responder_json(estado, datos)

    def _responder_archivo(self, archivo: "Archivo"):
        self.send_response(200)
        self.send_header("Content-Type", archivo.tipo)
        self.send_header("Content-Disposition", f'attachment; filename="{archivo.nombre}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(archivo.contenido)))
        self.end_headers()
        self.wfile.write(archivo.contenido)

    def _responder_json(self, estado: int, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):  # noqa: N802
        self._atender("GET")

    def do_POST(self):  # noqa: N802
        self._atender("POST")

    def do_DELETE(self):  # noqa: N802
        self._atender("DELETE")
