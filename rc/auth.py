"""Autorización: valida el token de Supabase Auth y el rol del usuario.

Roles: «admin» (OWNER_EMAIL, Reini: textos y todo lo demás), «diseno» (DISENO_EMAILS, Daniela: diseños y
animaciones) y «publicacion» (PUBLICACION_EMAILS, Luís: aprobación final y descargas). Las dos últimas variables
admiten varios correos separados por coma.
"""

import hmac
import json
import urllib.error
import urllib.request

from rc.config import env


class NoAutorizado(Exception):
    pass


def usuario_desde_token(cabecera_authorization: str | None) -> dict:
    if not cabecera_authorization or not cabecera_authorization.startswith("Bearer "):
        raise NoAutorizado("Falta el token")
    token = cabecera_authorization.removeprefix("Bearer ").strip()
    req = urllib.request.Request(
        f"{env('SUPABASE_URL').rstrip('/')}/auth/v1/user",
        headers={"apikey": env("SUPABASE_ANON_KEY"), "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            usuario = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise NoAutorizado("Token inválido o vencido") from e
    rol = rol_de((usuario.get("email") or "").lower())
    if not rol:
        raise NoAutorizado("Usuario no autorizado")
    return {**usuario, "rol": rol}


def _lista(nombre: str) -> set[str]:
    return {c.strip().lower() for c in (env(nombre, False) or "").split(",") if c.strip()}


def rol_de(email: str) -> str | None:
    if email and email == env("OWNER_EMAIL").lower():
        return "admin"
    if email in _lista("DISENO_EMAILS"):
        return "diseno"
    if email in _lista("PUBLICACION_EMAILS"):
        return "publicacion"
    return None


def es_cron_valido(cabecera_authorization: str | None) -> bool:
    secreto = env("CRON_SECRET")
    esperado = f"Bearer {secreto}"
    return bool(cabecera_authorization) and hmac.compare_digest(cabecera_authorization, esperado)
