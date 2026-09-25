"""Cliente mínimo de PostgREST (Supabase) con la librería estándar.

Usa la service_role key: solo debe ejecutarse en el servidor.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from rc.config import env

TIMEOUT_S = 20


class ErrorDB(Exception):
    def __init__(self, estado: int, detalle: str):
        super().__init__(f"PostgREST {estado}: {detalle}")
        self.estado = estado


def _solicitud(metodo: str, tabla: str, params: dict | None = None,
               cuerpo=None, prefer: str | None = None):
    url = f"{env('SUPABASE_URL').rstrip('/')}/rest/v1/{tabla}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="(),.*:")
    clave = env("SUPABASE_SERVICE_ROLE_KEY")
    cabeceras = {
        "apikey": clave,
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        cabeceras["Prefer"] = prefer
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            texto = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ErrorDB(e.code, e.read().decode("utf-8", "replace")) from e
    return json.loads(texto) if texto else None


def seleccionar(tabla: str, **params) -> list:
    """params son filtros PostgREST, p. ej. select="*", id="eq.5", order="semana"."""
    return _solicitud("GET", tabla, params)


def insertar(tabla: str, filas) -> list:
    return _solicitud("POST", tabla, cuerpo=filas, prefer="return=representation")


def actualizar(tabla: str, cambios: dict, **filtros) -> list:
    """Update condicional: devuelve las filas afectadas (lista vacía si ninguna)."""
    if not filtros:
        raise ValueError("actualizar() exige al menos un filtro")
    return _solicitud("PATCH", tabla, filtros, cuerpo=cambios, prefer="return=representation")


def borrar(tabla: str, **filtros) -> list:
    if not filtros:
        raise ValueError("borrar() exige al menos un filtro")
    return _solicitud("DELETE", tabla, filtros, prefer="return=representation")
