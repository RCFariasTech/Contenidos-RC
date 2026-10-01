"""Dominios confiables para la búsqueda web: viven en Supabase y se editan desde Configuración.

config/fuentes.json es la lista recomendada: semilla inicial y respaldo si la tabla no responde.
"""

import logging
import re
from urllib.parse import urlparse

from rc import db
from rc.config import cargar_json
from rc.errores import ErrorNegocio

log = logging.getLogger(__name__)

RE_DOMINIO = re.compile(r"^(?=.{4,100}$)([a-z0-9-]+\.)+[a-z]{2,}$")


def recomendadas() -> list[str]:
    return list(cargar_json("fuentes")["dominios"])


def normalizar(texto: str) -> str:
    """Acepta 'https://www.Kantar.com/informe', 'www.kantar.com' o 'kantar.com' y devuelve 'kantar.com'."""
    t = (texto or "").strip().lower()
    host = (urlparse(t if "://" in t else "//" + t).hostname or "").removeprefix("www.")
    if not RE_DOMINIO.match(host):
        raise ErrorNegocio("Escribe un dominio válido, por ejemplo kantar.com.")
    return host


def listar() -> list[str]:
    return sorted(f["dominio"] for f in db.seleccionar("fuentes_confiables", select="dominio"))


def dominios() -> list[str]:
    """Lista vigente para la búsqueda y el validador; cae a la recomendada si la tabla falla o está vacía."""
    try:
        lista = listar()
    except Exception:  # noqa: BLE001
        log.exception("No se pudo leer fuentes_confiables; se usa la lista recomendada")
        lista = []
    return lista or recomendadas()


def agregar(texto: str) -> str:
    dominio = normalizar(texto)
    try:
        db.insertar("fuentes_confiables", {"dominio": dominio})
    except db.ErrorDB as e:
        if e.estado == 409:
            raise ErrorNegocio(f"{dominio} ya está en la lista.") from e
        raise
    return dominio


def quitar(dominio: str) -> None:
    dominio = normalizar(dominio)
    if len(listar()) <= 1:
        raise ErrorNegocio("Debe quedar al menos una fuente: sin lista la búsqueda no tendría restricción.")
    if not db.borrar("fuentes_confiables", dominio=f"eq.{dominio}"):
        raise ErrorNegocio("Esa fuente ya no está en la lista.")


def restaurar() -> int:
    """Agrega las recomendadas que falten (no quita las que sumaste). Devuelve cuántas agregó."""
    faltan = [d for d in recomendadas() if d not in set(listar())]
    if faltan:
        db.insertar("fuentes_confiables", [{"dominio": d} for d in faltan])
    return len(faltan)
