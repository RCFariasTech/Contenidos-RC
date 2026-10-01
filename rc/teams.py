"""Aviso a Microsoft Teams por un webhook de Workflows (Power Automate), solo con librería estándar.

Teams ya no admite crear conectores de webhook entrantes nuevos: se usa un flujo con el disparador
"Cuando se recibe una solicitud de webhook de Teams", que recibe una Adaptive Card.
"""

import json
import logging
import urllib.error
import urllib.request

from rc.config import env
from rc.errores import ErrorNegocio

log = logging.getLogger(__name__)

APP_URL_POR_DEFECTO = "https://contenidos-rc.vercel.app"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def configurado() -> bool:
    return bool(env("TEAMS_WEBHOOK_URL", False))


def _tarjeta(titulo: str, texto: str, url_app: str) -> dict:
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": titulo, "weight": "Bolder", "size": "Medium", "wrap": True},
                    {"type": "TextBlock", "text": texto, "wrap": True, "spacing": "Small"},
                ],
                "actions": [{"type": "Action.OpenUrl", "title": "Abrir la app", "url": url_app}],
            },
        }],
    }


def _publicar(carga: dict) -> None:
    url = env("TEAMS_WEBHOOK_URL", False)
    if not url:
        raise ErrorNegocio("El aviso a Teams no está activado: falta TEAMS_WEBHOOK_URL en Vercel (ver README).")
    if not url.startswith("https://"):
        raise ErrorNegocio("TEAMS_WEBHOOK_URL debe ser una URL https.")
    req = urllib.request.Request(url, data=json.dumps(carga).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status >= 300:
                raise ErrorNegocio(f"Teams respondió {r.status}.")
    except urllib.error.HTTPError as e:
        raise ErrorNegocio(f"Teams rechazó el mensaje ({e.code}). Revisa el flujo de Workflows.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorNegocio("No se pudo conectar con Teams.") from e


def avisar_revision(mes_iso: str, piezas: int) -> bool:
    """Avisa que las propuestas del mes están listas. Nunca lanza: un fallo de Teams no debe romper la generación."""
    if not configurado():
        return False
    mes = f"{MESES[int(mes_iso[5:7]) - 1].capitalize()} {mes_iso[:4]}"
    try:
        _publicar(_tarjeta(f"Contenido de Instagram de {mes}: listo para revisión",
                           f"Ya están generadas las {piezas} propuestas. Revisa, comenta, ajusta y aprueba cada pieza.",
                           env("APP_URL", False) or APP_URL_POR_DEFECTO))
        return True
    except Exception:
        log.exception("No se pudo avisar a Teams")
        return False


def enviar_prueba() -> None:
    _publicar(_tarjeta("Prueba de aviso", "Si ves este mensaje, el aviso a Teams está bien configurado.",
                       env("APP_URL", False) or APP_URL_POR_DEFECTO))
