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
    ("POST", "comentarios"): ruta_comentar,
    ("DELETE", "comentarios"): ruta_borrar_comentario,
    ("POST", "aprobar"): ruta_aprobar,
    ("POST", "fecha"): ruta_fecha,
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
        self._responder_json(estado, datos)

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
