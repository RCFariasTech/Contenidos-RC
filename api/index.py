"""Única función serverless de la app (Vercel, runtime Python).

vercel.json reescribe /api/<ruta> → /api/index?ruta=<ruta>. Este archivo solo enruta;
la lógica vive en el paquete rc/.
"""

import json
import logging
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rc import auth, db  # noqa: E402
from rc.config import env  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

MAX_CUERPO = 64 * 1024


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


def ruta_yo(req):
    usuario = auth.usuario_desde_token(req["authorization"])
    meses = db.seleccionar("meses", select="id,mes_objetivo,estado", order="mes_objetivo.desc", limit="3")
    return 200, {"email": usuario.get("email"), "meses_recientes": meses}


def ruta_diario(req):
    if not auth.es_cron_valido(req["authorization"]):
        raise ErrorCliente(401, "No autorizado")
    # Fase 1: solo mantiene activo Supabase. El arranque mensual llega en la Fase 3.
    db.seleccionar("meses", select="id", limit="1")
    return 200, {"ok": True}


def ruta_diagnostico(req):
    """Pruebas de riesgo de la Fase 1. Protegido con CRON_SECRET."""
    if not auth.es_cron_valido(req["authorization"]):
        raise ErrorCliente(401, "No autorizado")
    prueba = req["query"].get("prueba", "db")
    if prueba == "db":
        filas = db.seleccionar("piezas", select="id,contenido->>tema_especifico", limit="10")
        return 200, {"ok": True, "piezas": filas}
    if prueba == "claude":
        from rc import generador  # import diferido: solo esta ruta necesita el SDK
        formato = req["query"].get("formato", "Carrusel")
        if formato not in ("Carrusel", "Reel"):
            raise ErrorCliente(400, "formato debe ser Carrusel o Reel")
        slot = {"semana": 1, "formato": formato, "tipo": "Tendencia",
                "pilar": "Tendencias de marketing BTL"}
        resultado = generador.generar(slot, historial=[], hermanas=[])
        return 200, resultado
    raise ErrorCliente(400, "prueba desconocida")


RUTAS = {
    ("GET", "config"): ruta_config,
    ("GET", "salud"): ruta_salud,
    ("GET", "yo"): ruta_yo,
    ("GET", "diario"): ruta_diario,
    ("GET", "diagnostico"): ruta_diagnostico,
}


# ---------- infraestructura HTTP ----------

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
        except json.JSONDecodeError:
            estado, datos = 400, {"error": "JSON inválido"}
        except Exception as e:  # noqa: BLE001
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
