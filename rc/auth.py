"""Autorización: valida el token de Supabase Auth y que sea el único usuario dueño."""

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
    email = (usuario.get("email") or "").lower()
    if email != env("OWNER_EMAIL").lower():
        raise NoAutorizado("Usuario no autorizado")
    return usuario


def es_cron_valido(cabecera_authorization: str | None) -> bool:
    secreto = env("CRON_SECRET")
    esperado = f"Bearer {secreto}"
    return bool(cabecera_authorization) and hmac.compare_digest(cabecera_authorization, esperado)
