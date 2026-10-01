"""Reglas deterministas de calidad de una pieza (PLAN.md 8.5 y 8.6)."""

import re
import unicodedata
from datetime import date
from urllib.parse import urlparse

from rc.esquema import CAMPOS_TEXTO

LIMITES = {
    "Carrusel": {"slide_1_gancho": 8, "slide_2": 30, "slide_3": 30, "slide_4": 30, "slide_5_cierre": 30},
    "Reel": {"escena_1_gancho": 6, "escena_2_desarrollo_a": 8, "escena_3_desarrollo_b": 8,
             "escena_4_desarrollo_c": 8, "escena_5_cta": 6},
}
ETIQUETAS = {
    "slide_1_gancho": "Tarjeta 1", "slide_2": "Tarjeta 2", "slide_3": "Tarjeta 3",
    "slide_4": "Tarjeta 4", "slide_5_cierre": "Tarjeta 5",
    "escena_1_gancho": "Escena 1", "escena_2_desarrollo_a": "Escena 2", "escena_3_desarrollo_b": "Escena 3",
    "escena_4_desarrollo_c": "Escena 4", "escena_5_cta": "Escena 5",
}
RE_ANIO = re.compile(r"\b(19|20)\d{2}\b")
RE_HASHTAG = re.compile(r"^#\w+$")
RE_RC_SIN_TILDE = re.compile(r"\bRC\s+Farias\b", re.IGNORECASE)

STOPWORDS = set("""
a al algo ante antes como con contra cual cuando de del desde donde dos el ella ellas ellos en entre era es esa
ese eso esta este esto estos estas fue ha hace hacia han hasta la las le les lo los mas me mi mucho muy nada ni
no nos o otra otro para pero poco por porque que quien se sea segun ser si sin sobre son su sus tal tambien tan
te tiene tienen todo todos tu un una unas uno unos y ya yo marca marcas
""".split())


def contar_palabras(texto: str) -> int:
    return sum(1 for t in (texto or "").split() if re.search(r"\w", t))


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def palabras_clave(texto: str) -> set[str]:
    return {p for p in re.findall(r"\w+", _normalizar(texto)) if p not in STOPWORDS and len(p) > 2}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def texto_similitud(contenido: dict) -> str:
    inv = contenido.get("investigacion") or {}
    return " ".join([contenido.get("tema_especifico", ""), inv.get("tendencia", ""),
                     inv.get("estrategia_clave", "")])


def _url_normalizada(url: str) -> str:
    return (url or "").split("?")[0].split("#")[0].rstrip("/").lower()


MESES_ES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
MESES_ES["setiembre"] = 9


def _fecha_fuente(texto: str) -> date | None:
    """Acepta AAAA-MM-DD, AAAA-MM y fechas en español ("24 de octubre de 2025", "octubre de 2025")."""
    texto = _normalizar(texto or "")
    try:
        m = re.search(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", texto)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
        m = re.search(r"(?:(\d{1,2}) de )?([a-z]+) (?:de |del )?(\d{4})", texto)
        if m and m.group(2) in MESES_ES:
            return date(int(m.group(3)), MESES_ES[m.group(2)], int(m.group(1) or 1))
    except ValueError:
        return None
    return None


def dominio_permitido(url: str, dominios: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in (x.split("/")[0].lower() for x in dominios))


PALABRAS_ENLACE = set("a al ante con contra de del desde e en entre hacia hasta la las lo los o para por que se según sin sobre su sus tras u un una unos unas y el".split())


def _palabras_texto(texto: str) -> list[str]:
    return re.findall(r"\w+", _normalizar(texto))


def _validar_diseno(pieza: dict) -> list[str]:
    """`diseno` parte cada tarjeta en titular + texto sin cambiar sus palabras (V13)."""
    diseno = pieza.get("diseno")
    campos = CAMPOS_TEXTO["Carrusel"]
    if not isinstance(diseno, list) or len(diseno) != len(campos):
        return [f'"diseno" debe tener exactamente {len(campos)} elementos, uno por tarjeta.']
    errores = []
    for i, (campo, d) in enumerate(zip(campos, diseno), 1):
        partes = f'{d.get("titular", "")} {d.get("texto", "")}'
        if _palabras_texto(partes) != _palabras_texto(pieza.get(campo, "")):
            errores.append(f"En diseno, titular + texto de la tarjeta {i} deben contener exactamente las mismas "
                           f"palabras, en el mismo orden, que {campo}.")
        if contar_palabras(d.get("titular", "")) > 10:
            errores.append(f"El titular de la tarjeta {i} tiene más de 10 palabras.")
        titular, texto = (d.get("titular") or "").strip(), (d.get("texto") or "").strip()
        if titular and texto:
            ultima = (_palabras_texto(titular) or [""])[-1]
            if ultima in PALABRAS_ENLACE or texto[0].islower():
                errores.append(f"En diseno, la tarjeta {i} parte una frase a la mitad: el titular debe ser una "
                               "oración completa con sentido propio y el texto debe comenzar una idea nueva (con mayúscula).")
        if not (d.get("ilustracion") or "").strip() and 1 <= i <= 4:
            errores.append(f"Falta la nota de ilustración de la tarjeta {i}.")
    return errores


def validar(formato: str, pieza: dict, urls_busqueda: list[str], previas: list[dict],
            hermanas: list[dict], ajustes: dict, hoy: date, dominios: list[str] | None = None) -> dict:
    """Devuelve {"errores": [...], "advertencias": [...], "reparables": [...]}.

    "reparables" son los errores que una llamada sin búsqueda web puede corregir.

    previas: contenidos del historial (incluye semillas con solo tema_especifico).
    hermanas: contenidos de las otras piezas del mes.
    """
    errores, advertencias, no_reparables = [], [], []

    # V1
    if pieza.get("formato") != formato:
        errores.append(f"El formato debe ser {formato}.")

    # V2 / V4: límites de palabras
    for campo, maximo in LIMITES[formato].items():
        n = contar_palabras(pieza.get(campo, ""))
        if n == 0:
            errores.append(f"{ETIQUETAS[campo]} está vacía.")
        elif n > maximo:
            errores.append(f"{ETIQUETAS[campo]} tiene {n} palabras (máximo {maximo}).")

    # V3
    if formato == "Carrusel":
        cierre = (pieza.get("slide_5_cierre") or "").lower()
        if "rc farías" not in cierre or "constellation" not in cierre:
            errores.append('La tarjeta 5 debe mencionar "RC Farías" (con tilde) y "Constellation".')

    if formato == "Carrusel":
        errores.extend(_validar_diseno(pieza))

    textos = [pieza.get(c, "") for c in CAMPOS_TEXTO[formato]] + [pieza.get("caption", "")]

    # Nombre de la agencia siempre con tilde: "RC Farias" sin tilde es un error en cualquier texto
    if any(RE_RC_SIN_TILDE.search(t or "") for t in textos):
        errores.append('El nombre debe escribirse "RC Farías" con tilde.')

    # V5: años
    if any(RE_ANIO.search(t or "") for t in textos):
        errores.append("Hay años específicos en las tarjetas/escenas o en el caption.")

    # V6: CTA
    cta = ajustes["cta"]
    if (pieza.get("cta") or "").strip() != cta:
        errores.append("El campo CTA no coincide con el CTA obligatorio.")
    if not (pieza.get("caption") or "").strip().endswith(cta):
        errores.append("El caption debe terminar exactamente con el CTA obligatorio.")

    # V7 / V8: hashtags y caption
    hashtags = pieza.get("hashtags") or []
    maximo = ajustes.get("hashtags_max", 3)
    if len(hashtags) > maximo:
        errores.append(f"Máximo {maximo} hashtags (tiene {len(hashtags)}); solo los que aporten alcance.")
    if len({_normalizar(h) for h in hashtags}) != len(hashtags):
        errores.append("Hay hashtags duplicados.")
    if any(not RE_HASHTAG.match(h) for h in hashtags):
        errores.append("Algún hashtag tiene un formato inválido.")
    prohibidos = {_normalizar(h) for h in ajustes["hashtags_prohibidos"]}
    usados_prohibidos = [h for h in hashtags if _normalizar(h) in prohibidos]
    if usados_prohibidos:
        errores.append(f"Hashtags prohibidos: {', '.join(usados_prohibidos)}.")
    palabras_caption = contar_palabras(pieza.get("caption", ""))
    if palabras_caption > ajustes["max_palabras_caption"]:
        errores.append(f"El caption tiene {palabras_caption} palabras (máximo {ajustes['max_palabras_caption']}).")

    # V9: fuente verificada (no reparable sin búsqueda)
    inv = pieza.get("investigacion") or {}
    url = inv.get("fuente_url") or ""
    if not url.startswith("https://"):
        no_reparables.append("La fuente debe ser una URL https.")
    elif dominios is not None and not dominio_permitido(url, dominios):
        no_reparables.append("La fuente no es de un dominio confiable de la lista aprobada.")
    elif _url_normalizada(url) not in {_url_normalizada(u) for u in urls_busqueda}:
        no_reparables.append("La fuente no aparece entre los resultados de la búsqueda web (posible URL inventada).")

    # V10: repetición (no reparable sin nueva búsqueda)
    propio = palabras_clave(texto_similitud(pieza))
    tema_propio = palabras_clave(pieza.get("tema_especifico", ""))
    for otro in previas + hermanas:
        if (otro or {}).get("semilla"):
            umbral, sim = ajustes["umbral_similitud_semillas"], jaccard(tema_propio, palabras_clave(otro.get("tema_especifico", "")))
        else:
            umbral, sim = ajustes["umbral_similitud"], jaccard(propio, palabras_clave(texto_similitud(otro or {})))
        if sim >= umbral:
            no_reparables.append(f'Posible repetición de "{otro.get("tema_especifico", "otro contenido")}". '
                                 'Comenta "cambia la tendencia" para investigar otra.')
            break

    # V11 / V12: advertencias
    fecha = _fecha_fuente(inv.get("fuente_fecha", ""))
    if fecha is None:
        if not _normalizar(inv.get("fuente_fecha", "")).strip().startswith("sin fecha visible"):
            advertencias.append("La fecha de la fuente no tiene un formato reconocible.")
        else:
            advertencias.append("La fuente no tiene fecha visible.")
    elif (hoy - fecha).days > ajustes["antiguedad_max_fuente_meses"] * 31:
        advertencias.append(f"La fuente tiene más de {ajustes['antiguedad_max_fuente_meses']} meses.")
    if not re.search(r"\d", inv.get("resumen", "")):
        advertencias.append("El resumen no incluye ninguna cifra o dato numérico.")

    return {"errores": errores + no_reparables, "advertencias": advertencias, "reparables": errores}
