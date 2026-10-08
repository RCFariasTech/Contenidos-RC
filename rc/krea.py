"""Cliente mínimo de la API pública de Krea (solo librería estándar) para generar ilustraciones 3D con el LoRA
«3d characters Flux». Las imágenes viven en Krea: aquí solo se envían trabajos y se consulta su estado.
"""

import json
import logging
import random
import urllib.error
import urllib.request

from rc.config import ajustes, env
from rc.errores import ErrorNegocio

log = logging.getLogger(__name__)

URL_BASE = "https://api.krea.ai"
TIMEOUT_S = 25
# Nombres simples de fondo, como en los prompts que mejor le funcionan al equipo en Krea
# («isolated in a red background», «isolated in a light gray background»).
NOMBRES_COLOR = {
    "coral": "red", "celeste": "light blue", "azul_medio": "blue",
    "gris_claro": "light gray", "azul_marino": "dark navy blue", "blanco": "white",
}


def configurado() -> bool:
    return bool(env("KREA_API_TOKEN", False))


def construir_prompt(descripcion: str, color: str, hex_fondo: str = "", composicion: str = "") -> str:
    """Prompt corto al estilo de las sesiones de RC en Krea: «3d of <escena>, isolated in a <color> background».

    Sin adornos de estilo ni códigos de color: el LoRA aporta el estilo y los prompts largos lo diluyen. El difuminado
    de bordes lo hace la app al montar la imagen en la tarjeta.
    """
    escena = " ".join(descripcion.split()).rstrip(" .")
    if not escena.lower().startswith("3d"):
        escena = f"3d of {escena[0].lower() + escena[1:]}" if escena else "3d character"
    escena = escena.split(", isolated in")[0]  # si ya traía fondo, se reemplaza por el de la tarjeta
    partes = [escena, composicion] if composicion else [escena]
    partes.append(f"isolated in a flat solid {NOMBRES_COLOR.get(color, color)} background")
    partes.append("seamless backdrop with no floor line and no horizon, only a minimal soft contact shadow where "
                  "it touches the surface, no long or cast shadows")
    return ", ".join(partes)[:1800]


def _motivo(cuerpo: str) -> str:
    """Texto breve con el motivo del rechazo, sea cual sea el formato de la respuesta de Krea."""
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        return " ".join(cuerpo.split())[:200]
    if isinstance(datos, dict):
        for clave in ("error", "message", "detail", "details", "errors"):
            if datos.get(clave):
                datos = datos[clave]
                break
    texto = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)
    return " ".join(texto.split())[:200]


def _peticion(metodo: str, ruta: str, cuerpo: dict | None = None):
    token = env("KREA_API_TOKEN", False).strip()
    if not token:
        raise ErrorNegocio("Las ilustraciones no están activadas: falta KREA_API_TOKEN en Vercel (ver README).")
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(f"{URL_BASE}{ruta}", data=datos, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        log.warning("Krea respondió %s: %s", e.code, detalle)
        if e.code in (401, 403):
            raise ErrorNegocio("Krea rechazó la clave de API (KREA_API_TOKEN). Revísala en Vercel.") from e
        if e.code == 402:
            raise ErrorNegocio("El saldo de API de Krea está en cero. Agrega saldo en Krea (sección API); es distinto de los créditos de la aplicación.") from e
        if e.code == 429:
            raise ErrorNegocio("Krea tiene demasiados trabajos en curso; intenta de nuevo en un momento.") from e
        motivo = _motivo(detalle)
        if e.code == 400 and ("no access" in motivo.lower() or "invalid ids" in motivo.lower()):
            raise ErrorNegocio("La clave de API de Krea no tiene acceso al modelo «3d characters Flux». "
                               "Crea una clave de tipo PERSONAL (no de servicio) con el usuario dueño del modelo y "
                               "reemplaza KREA_API_TOKEN en Vercel.") from e
        raise ErrorNegocio(f"Krea rechazó la solicitud ({e.code})" + (f": {motivo}" if motivo else ".")) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorNegocio("No se pudo conectar con Krea.") from e


PROPORCIONES_KREA2 = {"1:1": 1, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9, "4:5": 4 / 5, "3:4": 3 / 4, "2:3": 2 / 3, "9:16": 9 / 16}


def proporcion_cercana(ancho: int, alto: int) -> str:
    """La proporción admitida por Krea 2 más parecida a ancho/alto."""
    r = ancho / alto
    return min(PROPORCIONES_KREA2, key=lambda k: abs(PROPORCIONES_KREA2[k] - r))


def cuerpo_generacion(prompt: str, ancho: int, alto: int, guia: str | None = None) -> dict:
    """Parámetros según el modelo configurado: Flux (ancho/alto en px) o Krea 2 (proporción y resolución)."""
    k = ajustes()["krea"]
    base = {"prompt": prompt, "seed": random.randint(1, 2**31 - 1),
            "styles": [{"id": k["style_id"], "strength": k["style_strength"]}]}
    # Imágenes buenas del equipo (sesión «Character Choosing») como referencia de estilo, además del LoRA.
    referencias = [u for u in k.get("referencias_estilo", []) if str(u).startswith("https://")][:10]
    if referencias:
        base["image_style_references"] = [{"url": u, "strength": k.get("fuerza_referencias", 0.6)} for u in referencias]
    if k["modelo"].startswith("krea/krea-2"):
        return {**base, "aspect_ratio": proporcion_cercana(ancho, alto), "resolution": "1K",
                "creativity": k.get("creatividad", "raw")}
    cuerpo = {**base, "width": ancho, "height": alto, "steps": k["pasos"]}
    if guia:  # URL del boceto de composición: el personaje nace en su espacio (imagen a imagen)
        cuerpo["image_url"] = guia
        cuerpo["strength"] = k.get("fuerza_guia", 0.88)
    return cuerpo


def crear_trabajo(prompt: str, ancho: int, alto: int, guia: str | None = None) -> str:
    """Envía una generación con el LoRA y devuelve el id del trabajo. Si Krea rechaza el boceto, reintenta sin él."""
    ruta = f"/generate/image/{ajustes()['krea']['modelo']}"
    try:
        resp = _peticion("POST", ruta, cuerpo_generacion(prompt, ancho, alto, guia))
    except ErrorNegocio as e:
        if not guia or "(400)" not in str(e):
            raise
        log.warning("Krea rechazó el boceto de composición; se genera sin él: %s", e)
        resp = _peticion("POST", ruta, cuerpo_generacion(prompt, ancho, alto))
    job_id = resp.get("job_id")
    if not job_id:
        raise ErrorNegocio("Krea no devolvió el id del trabajo.")
    return job_id


def consultar(job_id: str) -> dict:
    """{"estado": "en_cola"|"lista"|"fallida", "url": str|None, "error": str|None}."""
    resp = _peticion("GET", f"/jobs/{job_id}")
    estado = resp.get("status")
    if estado == "completed":
        urls = ((resp.get("result") or {}).get("urls")) or []
        url = urls[0] if urls and str(urls[0]).startswith("https://") else None
        return {"estado": "lista" if url else "fallida", "url": url,
                "error": None if url else "Krea terminó sin devolver una imagen."}
    if estado in ("failed", "cancelled"):
        return {"estado": "fallida", "url": None, "error": ((resp.get("error") or {}).get("message")) or "Krea no pudo generarla."}
    return {"estado": "en_cola", "url": None, "error": None}
