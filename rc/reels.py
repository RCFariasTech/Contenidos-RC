"""Guion visual de un reel en PDF vertical 9:16 (1080 x 1920): una página por escena.

Cada página trae el texto en pantalla (editable), el espacio para la imagen o el video y los tiempos.
El diseñador lo abre en Adobe Express ("Empezar con tu contenido"), inserta los medios y anima.
Todo queda dentro de la zona segura de Instagram (sin texto en los ~220 px de arriba ni los ~450 px de abajo).
"""

import io
import re

from reportlab.pdfgen import canvas

from rc import tarjetas
from rc.tarjetas import M, NEGRITA, NORMAL, MUY_NEGRITA, PORTADAS, Lienzo, ajustar

W, H = 1080, 1920
ZONA_ARRIBA, ZONA_ABAJO = 220, 450
CAMPOS = ("escena_1_gancho", "escena_2_desarrollo_a", "escena_3_desarrollo_b",
          "escena_4_desarrollo_c", "escena_5_cta")
ROLES = (("Gancho", "0–5 s"), ("Desarrollo", "5–12 s"), ("Desarrollo", "12–20 s"),
         ("Desarrollo", "20–25 s"), ("CTA", "25–30 s"))


def _pagina(L, numero: int, texto: str, variante: int) -> None:
    fondo, c_texto, c_apoyo, oscuro = PORTADAS[variante % len(PORTADAS)]
    rol, tiempo = ROLES[numero - 1]
    c = L.c
    L.fondo(fondo)
    # Etiqueta de la escena (dentro de la zona segura)
    L.bloque(f"ESCENA {numero} · {rol.upper()} · {tiempo}", NEGRITA, c_apoyo, M, ZONA_ARRIBA + 20,
             W - 2 * M, 50, 34)
    # Espacio para la imagen o el video
    y_caja, alto_caja = ZONA_ARRIBA + 110, 800
    tinta = L.col["blanco"] if oscuro else L.col["azul_marino"]
    c.saveState()
    c.setFillColor(tinta)
    c.setFillAlpha(0.14 if oscuro else 0.10)
    c.setStrokeColor(tinta)
    c.setStrokeAlpha(0.75)
    c.setLineWidth(3)
    c.setDash(14, 10)
    c.roundRect(M, H - y_caja - alto_caja, W - 2 * M, alto_caja, 36, stroke=1, fill=1)
    c.restoreState()
    c.setFillColor(tinta)
    c.setFont(NEGRITA, 30)
    c.drawCentredString(W / 2, H - y_caja - alto_caja / 2 + 10, "IMAGEN O VIDEO")
    c.setFont(NORMAL, 24)
    c.drawCentredString(W / 2, H - y_caja - alto_caja / 2 - 28, f"Escena {numero} · {tiempo}")
    # Texto en pantalla
    y_texto = y_caja + alto_caja + 60
    L.bloque(texto, MUY_NEGRITA, c_texto, M, y_texto, W - 2 * M, H - ZONA_ABAJO - y_texto, 96, inter=1.12)


def generar_pdf(contenido: dict, titulo: str = "Reel", variante: int = 0) -> bytes:
    tarjetas._registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, tarjetas._colores(), alto=H, ancho=W)
    for i, campo in enumerate(CAMPOS, 1):
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante)
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    return tarjetas.nombre_archivo(contenido, mes_iso).replace("tarjetas-", "guion-visual-reel-", 1)
