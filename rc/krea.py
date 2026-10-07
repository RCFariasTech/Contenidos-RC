"""Cliente mínimo de la API pública de Krea (solo librería estándar) para generar ilustraciones 3D con el LoRA
«3d characters in red and blue». Las imágenes viven en Krea: aquí solo se envían trabajos y se consulta su estado.
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
NOMBRES_COLOR = {
    "coral": "coral red", "celeste": "light sky blue", "azul_medio": "medium royal blue",
    "gris_claro": "light warm gray", "azul_marino": "deep navy blue", "blanco": "pure white",
}


def configurado() -> bool:
    return bool(env("KREA_API_TOKEN", False))


def construir_prompt(descripcion: str, color: str, hex_fondo: str) -> str:
    """Prompt en inglés: la escena que pide el modelo + estilo + fondo del color de la tarjeta con bordes difuminados."""
    return (
        f"krea, high resolution. {descripcion.strip().rstrip('.')}. "
        "Friendly 3D rendered characters in red and blue, smooth glossy toy-like 3D style, soft studio lighting. "
        f"Solid flat {NOMBRES_COLOR.get(color, color)} ({hex_fondo}) background filling the whole frame, no gradients, "
        "no text, no logos; the edges of the image blur softly and fade into the background color."
    )[:1800]


def _peticion(metodo: str, ruta: str, cuerpo: dict | None = None):
    token = env("KREA_API_TOKEN", False)
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
        try:  # el motivo que da Krea (sin datos sensibles) ayuda a diagnosticar
            motivo = json.loads(detalle).get("error")
        except (ValueError, AttributeError):
            motivo = detalle
        motivo = " ".join(str(motivo or "").split())[:200]
        raise ErrorNegocio(f"Krea rechazó la solicitud ({e.code})" + (f": {motivo}" if motivo else ".")) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorNegocio("No se pudo conectar con Krea.") from e


def crear_trabajo(prompt: str, ancho: int, alto: int) -> str:
    """Envía una generación con el LoRA y devuelve el id del trabajo."""
    k = ajustes()["krea"]
    resp = _peticion("POST", f"/generate/image/{k['modelo']}", {
        "prompt": prompt, "width": ancho, "height": alto, "steps": k["pasos"],
        "seed": random.randint(1, 2**31 - 1),
        "styles": [{"id": k["style_id"], "strength": k["style_strength"]}],
    })
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
