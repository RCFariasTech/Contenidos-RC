"""Llamadas a Claude para generar, ajustar y reparar piezas (PLAN.md, sección 8)."""

import json
import logging
import time

import anthropic

from rc import prompts
from rc import fuentes
from rc.config import ajustes, env
from rc.esquema import ESQUEMA_PIEZA

log = logging.getLogger(__name__)

MAX_TOKENS_TOPE = 64000


class ErrorGeneracion(Exception):
    pass


def clave_anthropic() -> str:
    """Clave de Anthropic: ANTHROPIC_API_KEY2 (si existe) o ANTHROPIC_API_KEY, sin espacios ni saltos de línea."""
    return (env("ANTHROPIC_API_KEY2", False) or env("ANTHROPIC_API_KEY", False)).strip()


def _cliente() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=clave_anthropic() or None)


def _sumar_uso(total: dict, uso) -> None:
    if uso is None:
        return
    datos = uso.model_dump() if hasattr(uso, "model_dump") else dict(uso)
    for clave in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens"):
        total[clave] = total.get(clave, 0) + (datos.get(clave) or 0)
    busquedas = (datos.get("server_tool_use") or {}).get("web_search_requests") or 0
    total["web_search_requests"] = total.get("web_search_requests", 0) + busquedas


def _pista_clave(clave: str) -> str:
    """Datos no secretos para diagnosticar una clave mal pegada: tipo (prefijo fijo) y largo."""
    if clave.startswith("sk-ant-api"):
        tipo = "es una clave de API (correcto)"
    elif clave.startswith("sk-ant-admin"):
        tipo = "es una clave de ADMINISTRACIÓN, que no sirve para generar: crea una clave de API normal"
    elif clave.startswith("sk-ant-"):
        tipo = "es una clave de Anthropic de otro tipo (no de API)"
    else:
        tipo = "no tiene el formato de una clave de API de Anthropic (debe empezar con sk-ant-api)"
    return f"La clave guardada {tipo} y tiene {len(clave)} caracteres (una clave de API completa tiene alrededor de 100)."


def verificar_clave() -> dict:
    """Comprueba la clave de Anthropic listando un modelo (no genera texto ni consume tokens)."""
    if not clave_anthropic():
        return {"ok": False, "detalle": "Falta la clave de Anthropic en Vercel (ANTHROPIC_API_KEY2 o ANTHROPIC_API_KEY)."}
    try:
        _cliente().models.list(limit=1)
    except anthropic.AuthenticationError:
        return {"ok": False, "detalle": "Anthropic no reconoce la clave: revisa que se haya copiado completa y que no esté borrada en la consola. "
                + _pista_clave(clave_anthropic())}
    except anthropic.PermissionDeniedError:
        return {"ok": False, "detalle": "La clave existe pero no tiene permisos para usar la API."}
    except anthropic.APIConnectionError:
        return {"ok": False, "detalle": "No se pudo conectar con Anthropic; intenta de nuevo."}
    except anthropic.APIStatusError as e:
        return {"ok": False, "detalle": f"Anthropic respondió con error {e.status_code}."}
    return {"ok": True, "detalle": "Clave válida."}


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
    busqueda = {"type": "web_search_20260209", "name": "web_search", "max_uses": max_busquedas}
    if a.get("fuentes_estrictas"):  # solo si se vuelve al modo estricto: búsqueda limitada a la lista aprobada
        busqueda["allowed_domains"] = fuentes.dominios()
    herramientas = [busqueda] if max_busquedas else []
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


SISTEMAS_IMAGEN = {
    "icono": (
        "Propones la ilustración vectorial editorial que acompaña una tarjeta de carrusel (o la escena 1 de un reel) "
        "de Instagram sobre marketing BTL y experiencial (RC Farías, Colombia). Es una imagen de APOYO: convierte la "
        "idea central en UNA metáfora visual conceptual (ajedrez = estrategia, bombillo = concepto, mano = acción), "
        "en composición tipo bodegón con pocos objetos grandes. No intenta representar todo el texto. Si hay "
        "personas, son abstractas y sin rostro.\n"
        "Responde EN ESPAÑOL con exactamente este formato, en una sola línea (máximo 45 palabras en total):\n"
        "Escena: <la metáfora en una frase>. Protagonista: <el elemento principal>. Apoyo: <2 o 3 elementos simples>. "
        "Punto focal: <UN detalle clave del protagonista, que irá en rojo>.\n"
        "Ejemplo: «Escena: una estrategia de evento que gana la partida. Protagonista: un rey de ajedrez grande. "
        "Apoyo: un tablero en perspectiva y dos peones. Punto focal: la corona del rey.»\n"
        "Sin palabras de estilo, colores, fondo, textos, letras, números, logos ni marcas."
    ),
    "linea": (
        "Describes el tema de UN ícono de línea minimalista (pictograma simple) para una tarjeta de carrusel de "
        "Instagram sobre marketing BTL y experiencial. A partir del texto de la tarjeta, responde con UNA descripción "
        "breve EN ESPAÑOL (5 a 15 palabras) de un solo símbolo o un par de elementos simples que representen la idea "
        "(ej.: una lupa sobre un gráfico de barras; un carrito de compras con una flecha hacia arriba). Sin estilo, "
        "colores, fondo, textos, letras, números ni logos."
    ),
    "foto": (
        "Describes UNA foto documental realista para una tarjeta de carrusel de Instagram sobre marketing BTL y "
        "experiencial en Colombia. La foto SIEMPRE muestra un evento o activación de marca con tecnología: pantallas "
        "LED grandes, gafas de realidad virtual, simuladores, hologramas, pantallas táctiles, juegos multimedia o "
        "activaciones phygital. A partir del texto de la tarjeta, responde con UNA descripción de la escena EN "
        "ESPAÑOL (15 a 40 palabras): quién (personas latinas comunes de clase media, edad y género), dónde (evento, "
        "centro comercial, punto de venta, feria) y qué tecnología usan. Sin palabras de estilo ni de cámara, sin "
        "textos, letreros, logos ni marcas."
    ),
}


def describir_ilustracion(tema: str, titular: str, texto: str, nota: str = "", tipo: str = "icono",
                          evitar: list[str] | None = None) -> str:
    """Descripción EN ESPAÑOL de qué mostrar (ilustración vectorial, ícono de línea o foto), a partir del texto de la
    tarjeta. `evitar`: sugerencias anteriores, para proponer una opción distinta."""
    usuario = (f"Tema del carrusel: {tema}\nTitular de la tarjeta: {titular}\nTexto de la tarjeta: {texto}\n"
               + (f"Nota del diseñador: {nota}\n" if nota else ""))
    previas = [" ".join(p.split()) for p in (evitar or []) if p and p.strip()][-6:]
    if previas:
        usuario += ("Ya se propusieron estas opciones; propone una idea claramente DISTINTA (otros objetos u otra "
                    "situación):\n" + "\n".join(f"- {p}" for p in previas) + "\n")
    sistema = SISTEMAS_IMAGEN.get(tipo, SISTEMAS_IMAGEN["foto"]) + " Responde solo con la descripción."
    try:
        respuesta = _cliente().messages.create(
            # Modelo rápido: es una descripción corta y el usuario espera con el panel abierto.
            model=ajustes().get("modelo_sugerencias") or ajustes()["modelo"], max_tokens=1500, system=sistema,
            messages=[{"role": "user", "content": usuario}])
    except anthropic.APIError as e:
        raise ErrorGeneracion(f"No se pudo sugerir la descripción: {e}") from e
    descripcion = " ".join(b.text for b in respuesta.content if getattr(b, "type", None) == "text").strip()
    if not descripcion:
        log.warning("Sugerencia de imagen vacía (stop_reason=%s)", getattr(respuesta, "stop_reason", "?"))
        raise ErrorGeneracion("El modelo no devolvió la descripción; intenta de nuevo.")
    return " ".join(descripcion.split()).strip('"«»').strip()[:500]


def proponer_gancho(formato: str, contenido: dict, evitar: list[str], max_palabras: int) -> str:
    """Un gancho nuevo para la pieza (tarjeta 1 o escena 1), distinto de los anteriores. Sin búsqueda web."""
    campos = {"Carrusel": ("slide_2", "slide_3", "slide_4", "slide_5_cierre"),
                               "Reel": ("escena_2_desarrollo_a", "escena_3_desarrollo_b", "escena_4_desarrollo_c",
                                        "escena_5_cta")}[formato]
    resto = "\n".join(f"- {contenido.get(c, '')}" for c in campos)
    previos = "\n".join(f"- {g}" for g in evitar if g)
    usuario = (f"Formato: {formato} de Instagram de RC Farías (agencia BTL de Colombia).\n"
               f"Tema: {contenido.get('tema_especifico', '')}\nResto del contenido:\n{resto}\n"
               f"Ganchos ya usados (propón uno claramente DISTINTO):\n{previos}\n\n"
               f"Escribe UN gancho nuevo en español, de máximo {max_palabras} palabras: una afirmación provocadora o "
               "una pregunta disruptiva, coherente con el resto del contenido, sin hashtags ni emojis y sin inventar "
               "datos. Responde solo con el gancho.")
    try:
        respuesta = _cliente().messages.create(
            model=ajustes()["modelo"], max_tokens=300,
            system="Eres redactor creativo senior de una agencia de marketing BTL y experiencial.",
            messages=[{"role": "user", "content": usuario}], output_config={"effort": "low"})
    except anthropic.APIError as e:
        raise ErrorGeneracion(f"No se pudo proponer un gancho: {e}") from e
    gancho = " ".join(b.text for b in respuesta.content if getattr(b, "type", None) == "text").strip()
    gancho = " ".join(gancho.split()).strip('"«»“”').strip()
    if not gancho:
        raise ErrorGeneracion("El modelo no devolvió un gancho.")
    return gancho


def generar(slot: dict, historial: list[dict], hermanas: list[dict], descartados: list[dict] | None = None) -> dict:
    usuario = prompts.generar(slot, historial, hermanas, descartados)
    return llamar(usuario, slot["formato"], ajustes()["web_search_max_uses_generar"])


def ajustar(slot: dict, pieza: dict, comentarios: list[str], historial: list[dict],
            hermanas: list[dict]) -> dict:
    usuario = prompts.ajustar(pieza, comentarios, historial, hermanas)
    return llamar(usuario, slot["formato"], ajustes()["web_search_max_uses_ajustar"], effort="low")


def reparar(slot: dict, pieza: dict, errores: list[str]) -> dict:
    return llamar(prompts.reparar(pieza, errores), slot["formato"], 0, effort="low")
