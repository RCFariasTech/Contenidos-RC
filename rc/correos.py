"""Correos favoritos y envío del PowerPoint por SMTP (solo librería estándar)."""

import re
import smtplib
import ssl
from email.message import EmailMessage

from rc import db
from rc.config import env
from rc.errores import ErrorNegocio

RE_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
MAX_DESTINATARIOS = 10
TIPO_PPTX = ("application", "vnd.openxmlformats-officedocument.presentationml.presentation")


def validar_email(texto: str) -> str:
    email = (texto or "").strip().lower()
    if len(email) > 254 or not RE_EMAIL.match(email):
        raise ErrorNegocio(f"«{texto}» no parece un correo válido.")
    return email


def separar_correos(texto: str) -> list[str]:
    """Acepta varios correos separados por coma, punto y coma, espacio o salto de línea."""
    return [validar_email(t) for t in re.split(r"[,;\s]+", texto or "") if t.strip()]


# ---------- favoritos ----------

def listar_favoritos() -> list[dict]:
    return db.seleccionar("correos_favoritos", select="id,email,nombre", order="email")


def agregar_favorito(email: str, nombre: str | None = None) -> dict:
    email = validar_email(email)
    nombre = (nombre or "").strip()[:100] or None
    try:
        return db.insertar("correos_favoritos", {"email": email, "nombre": nombre})[0]
    except db.ErrorDB as e:
        if e.estado == 409:
            raise ErrorNegocio(f"{email} ya está en tus favoritos.") from e
        raise


def borrar_favorito(favorito_id: int) -> None:
    if not db.borrar("correos_favoritos", id=f"eq.{int(favorito_id)}"):
        raise ErrorNegocio("Ese favorito ya no existe.")


# ---------- envío ----------

def configurado() -> bool:
    return bool(env("SMTP_USER", False) and env("SMTP_PASSWORD", False))


def enviar(destinatarios: list[str], asunto: str, cuerpo: str, adjunto: bytes, nombre_adjunto: str) -> None:
    if not configurado():
        raise ErrorNegocio("El envío por correo aún no está configurado: faltan SMTP_USER y SMTP_PASSWORD en Vercel.")
    if not destinatarios:
        raise ErrorNegocio("Elige al menos un destinatario.")
    if len(destinatarios) > MAX_DESTINATARIOS:
        raise ErrorNegocio(f"Máximo {MAX_DESTINATARIOS} destinatarios por envío.")
    usuario = env("SMTP_USER")
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"RC Farías · Contenido <{env('SMTP_FROM', False) or usuario}>"
    msg["To"] = ", ".join(destinatarios)
    if env("OWNER_EMAIL", False):
        msg["Reply-To"] = env("OWNER_EMAIL")
    msg.set_content(cuerpo)
    msg.add_attachment(adjunto, maintype=TIPO_PPTX[0], subtype=TIPO_PPTX[1], filename=nombre_adjunto)
    try:
        with smtplib.SMTP(env("SMTP_HOST", False) or "smtp.gmail.com", int(env("SMTP_PORT", False) or 587),
                          timeout=25) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(usuario, env("SMTP_PASSWORD"))
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise ErrorNegocio("El servidor de correo rechazó el usuario o la contraseña de aplicación.") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise ErrorNegocio("El servidor rechazó a todos los destinatarios.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise ErrorNegocio(f"No se pudo enviar el correo: {e}") from e
