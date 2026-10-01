"""Carga de configuración: archivos de config/ y variables de entorno."""

import json
import os
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=None)
def cargar_json(nombre: str) -> dict:
    with open(RAIZ / "config" / f"{nombre}.json", encoding="utf-8") as f:
        return json.load(f)


def ajustes() -> dict:
    return cargar_json("ajustes")


def pilares() -> dict:
    return cargar_json("pilares")


def specs_instagram() -> dict:
    return cargar_json("instagram_specs")


def marca() -> dict:
    return cargar_json("marca")


def env(nombre: str, obligatoria: bool = True) -> str:
    valor = os.environ.get(nombre, "")
    if obligatoria and not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor
