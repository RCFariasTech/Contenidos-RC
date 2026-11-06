"""Cliente mínimo de la API pública de Krea (solo librería estándar): íconos isométricos y fotos con Nano Banana Pro.
Las imágenes viven en Krea: aquí solo se envían trabajos y se consulta su estado.
"""

import json
import logging
import urllib.error
import urllib.request

from rc.config import ajustes, env
from rc import estilo_iconos
from rc.errores import ErrorNegocio

log = logging.getLogger(__name__)

URL_BASE = "https://api.krea.ai"
TIMEOUT_S = 25


def configurado() -> bool:
    return bool(env("KREA_API_TOKEN", False))


def construir_prompt(descripcion: str, tipo: str) -> str:
    """Prompt completo para Krea: «icono» (isométrico, tarjeta 1), «foto» (tarjeta 2) o «linea» (tarjeta 3)."""
    escena = " ".join((descripcion or "").split()).strip(" .\"")
    fn = {"icono": estilo_iconos.prompt_icono, "linea": estilo_iconos.prompt_linea}.get(tipo, estilo_iconos.prompt_foto)
    return fn(escena)[:3000]


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
        raise ErrorNegocio(f"Krea rechazó la solicitud ({e.code})" + (f": {motivo}" if motivo else ".")) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorNegocio("No se pudo conectar con Krea.") from e


def cuerpo_generacion(prompt: str, proporcion: str, referencias: list[str] | None = None) -> dict:
    """Parámetros de Nano Banana Pro: proporción, resolución y (íconos) imágenes de referencia de estilo."""
    k = ajustes()["krea"]
    cuerpo = {"prompt": prompt, "aspect_ratio": proporcion, "resolution": k.get("resolucion", "1K")}
    urls = [u for u in (referencias or []) if str(u).startswith("https://")][:6]
    if urls:
        cuerpo["image_urls"] = urls
    return cuerpo


def crear_trabajo(prompt: str, proporcion: str, referencias: list[str] | None = None) -> str:
    """Envía una generación y devuelve el id del trabajo."""
    resp = _peticion("POST", f"/generate/image/{ajustes()['krea']['modelo']}",
                     cuerpo_generacion(prompt, proporcion, referencias))
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
