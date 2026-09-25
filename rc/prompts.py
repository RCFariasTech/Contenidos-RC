"""Armado de prompts a partir de las plantillas de prompts/ (string.Template)."""

import json
from functools import lru_cache
from string import Template

from rc.config import RAIZ, ajustes, pilares


@lru_cache(maxsize=None)
def _plantilla(nombre: str) -> Template:
    return Template((RAIZ / "prompts" / f"{nombre}.md").read_text(encoding="utf-8"))


def _lineas_resumen(piezas: list[dict]) -> str:
    """Una línea por pieza: mes | pilar | tema | tendencia | estrategia."""
    lineas = []
    for p in piezas:
        c = p.get("contenido") or {}
        inv = c.get("investigacion") or {}
        partes = [p.get("mes", ""), p.get("pilar", ""), c.get("tema_especifico", ""),
                  inv.get("tendencia", ""), inv.get("estrategia_clave", "")]
        lineas.append("- " + " | ".join(x for x in partes if x))
    return "\n".join(lineas) or "(sin registros)"


def sistema() -> str:
    a = ajustes()
    temas = "\n".join(f'- "{t}"' for t in pilares()["temas_ya_usados"])
    return _plantilla("sistema").substitute(
        cta=a["cta"], temas_ya_usados=temas, max_palabras_caption=a["max_palabras_caption"])


def generar(slot: dict, historial: list[dict], hermanas: list[dict]) -> str:
    return _plantilla("generar").substitute(
        historial=_lineas_resumen(historial), hermanas=_lineas_resumen(hermanas),
        semana=slot["semana"], formato=slot["formato"], tipo=slot["tipo"], pilar=slot["pilar"])


def ajustar(pieza: dict, comentarios: list[str], historial: list[dict],
            hermanas: list[dict]) -> str:
    return _plantilla("ajustar").substitute(
        comentarios="\n".join(f"- {c}" for c in comentarios),
        historial=_lineas_resumen(historial), hermanas=_lineas_resumen(hermanas),
        pieza_json=json.dumps(pieza, ensure_ascii=False, indent=2))


def reparar(pieza: dict, errores: list[str]) -> str:
    return _plantilla("reparar").substitute(
        errores="\n".join(f"- {e}" for e in errores),
        pieza_json=json.dumps(pieza, ensure_ascii=False, indent=2))
