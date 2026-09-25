"""Llamadas a Claude para generar, ajustar y reparar piezas (PLAN.md, sección 8)."""

import json
import logging
import time

import anthropic

from rc import prompts
from rc.config import ajustes
from rc.esquema import ESQUEMA_PIEZA

log = logging.getLogger(__name__)

MAX_TOKENS_TOPE = 64000


class ErrorGeneracion(Exception):
    pass


def _cliente() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # lee ANTHROPIC_API_KEY


def _sumar_uso(total: dict, uso) -> None:
    if uso is None:
        return
    datos = uso.model_dump() if hasattr(uso, "model_dump") else dict(uso)
    for clave in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens"):
        total[clave] = total.get(clave, 0) + (datos.get(clave) or 0)
    busquedas = (datos.get("server_tool_use") or {}).get("web_search_requests") or 0
    total["web_search_requests"] = total.get("web_search_requests", 0) + busquedas


def urls_de_busqueda(contenido) -> list[str]:
    """URLs devueltas por web_search. Un error de búsqueda llega como objeto, no como lista."""
    urls = []
    for bloque in contenido:
        if getattr(bloque, "type", None) != "web_search_tool_result":
            continue
        resultado = getattr(bloque, "content", None)
        if isinstance(resultado, list):
            urls.extend(r.url for r in resultado if getattr(r, "url", None))
        else:
            log.warning("web_search devolvió error: %s", getattr(resultado, "error_code", resultado))
    return urls


def _json_del_ultimo_texto(contenido) -> dict:
    textos = [b.text for b in contenido if getattr(b, "type", None) == "text"]
    if not textos:
        raise ErrorGeneracion("La respuesta no contiene texto")
    texto = textos[-1].strip()
    if texto.startswith("```"):  # por si en el Plan B el modelo envuelve el JSON
        texto = texto.strip("`").removeprefix("json").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErrorGeneracion(f"JSON inválido en la respuesta: {e}") from e


def llamar(usuario: str, formato: str, max_busquedas: int, effort: str | None = None) -> dict:
    """Una llamada completa (con reanudaciones de pause_turn).

    Devuelve {"pieza", "urls", "uso", "duracion_s", "modelo", "formato_estructurado"}.
    max_busquedas = 0 significa sin herramienta de búsqueda (reparaciones).
    """
    a = ajustes()
    esquema = ESQUEMA_PIEZA[formato]
    sistema = prompts.sistema()
    herramientas = ([{"type": "web_search_20260209", "name": "web_search",
                      "max_uses": max_busquedas}] if max_busquedas else [])
    usar_formato = a.get("formato_estructurado", True)
    max_tokens = a["max_tokens"]
    mensajes = [{"role": "user", "content": usuario}]
    urls: list[str] = []
    uso: dict = {}
    inicio = time.monotonic()
    reanudaciones = 0
    reintento_max_tokens = False

    while True:
        output_config = {"effort": effort or a["effort"]}
        sistema_final = sistema
        if usar_formato:
            output_config["format"] = {"type": "json_schema", "schema": esquema}
        else:  # Plan B (PLAN.md 8.1): esquema en el prompt
            sistema_final += ("\n\nESQUEMA JSON OBLIGATORIO (responde solo con el JSON, sin texto extra):\n"
                              + json.dumps(esquema, ensure_ascii=False))
        params = dict(model=a["modelo"], max_tokens=max_tokens, system=sistema_final,
                      messages=mensajes, output_config=output_config)
        if herramientas:
            params["tools"] = herramientas
        try:
            with _cliente().messages.stream(**params) as stream:
                respuesta = stream.get_final_message()
        except anthropic.BadRequestError as e:
            if usar_formato and max_busquedas and reanudaciones == 0:
                log.warning("Structured outputs rechazado junto a web_search; se usa el Plan B: %s", e)
                usar_formato = False
                continue
            raise ErrorGeneracion(f"Solicitud rechazada por la API: {e}") from e
        except anthropic.RateLimitError as e:
            raise ErrorGeneracion("Límite de uso de la API alcanzado; reintenta en unos minutos") from e
        except anthropic.APIStatusError as e:
            raise ErrorGeneracion(f"Error de la API ({e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise ErrorGeneracion("No se pudo conectar con la API de Anthropic") from e

        _sumar_uso(uso, respuesta.usage)
        urls.extend(urls_de_busqueda(respuesta.content))

        if respuesta.stop_reason == "pause_turn":
            reanudaciones += 1
            if reanudaciones > a["max_reanudaciones_pause_turn"]:
                raise ErrorGeneracion("Demasiadas reanudaciones (pause_turn)")
            mensajes = [*mensajes, {"role": "assistant", "content": respuesta.content}]
            continue
        if respuesta.stop_reason == "refusal":
            detalle = getattr(respuesta, "stop_details", None)
            raise ErrorGeneracion(f"El modelo rechazó la solicitud: {detalle}")
        if respuesta.stop_reason == "max_tokens":
            if reintento_max_tokens:
                raise ErrorGeneracion("La respuesta superó el máximo de tokens")
            reintento_max_tokens = True
            max_tokens = min(max_tokens * 2, MAX_TOKENS_TOPE)
            mensajes = [{"role": "user", "content": usuario}]
            urls, reanudaciones = [], 0
            continue
        break

    return {
        "pieza": _json_del_ultimo_texto(respuesta.content),
        "urls": urls,
        "uso": uso,
        "duracion_s": round(time.monotonic() - inicio, 1),
        "modelo": respuesta.model,
        "formato_estructurado": usar_formato,
    }


def generar(slot: dict, historial: list[dict], hermanas: list[dict]) -> dict:
    usuario = prompts.generar(slot, historial, hermanas)
    return llamar(usuario, slot["formato"], ajustes()["web_search_max_uses_generar"])


def ajustar(slot: dict, pieza: dict, comentarios: list[str], historial: list[dict],
            hermanas: list[dict]) -> dict:
    usuario = prompts.ajustar(pieza, comentarios, historial, hermanas)
    return llamar(usuario, slot["formato"], ajustes()["web_search_max_uses_ajustar"], effort="low")


def reparar(slot: dict, pieza: dict, errores: list[str]) -> dict:
    return llamar(prompts.reparar(pieza, errores), slot["formato"], 0, effort="low")
