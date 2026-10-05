"""Guion visual de un reel en PDF vertical 9:16 (1080 x 1920): una página por escena.

Cada página trae el texto en pantalla (editable), el espacio para la imagen o el video y los tiempos.
El diseñador lo abre en Adobe Express ("Empezar con tu contenido"), inserta los medios y anima.
Todo queda dentro de la zona segura de Instagram (sin texto en los ~220 px de arriba ni los ~450 px de abajo).
"""

import io
import re

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from rc import tarjetas
from rc.config import RAIZ, marca
from rc.tarjetas import M, NEGRITA, NORMAL, MUY_NEGRITA, PORTADAS, Lienzo, ajustar

W, H = 1080, 1920
ZONA_ARRIBA, ZONA_ABAJO = 220, 450
CAMPOS = ("escena_1_gancho", "escena_2_desarrollo_a", "escena_3_desarrollo_b",
          "escena_4_desarrollo_c", "escena_5_cta")
ROLES = (("Gancho", "0–5 s"), ("Desarrollo", "5–12 s"), ("Desarrollo", "12–20 s"),
         ("Desarrollo", "20–25 s"), ("CTA", "25–30 s"))


def _pagina(L, numero: int, texto: str, variante: int) -> None:
    # Cada escena cambia de color de fondo, como las tarjetas del carrusel.
    fondo, c_texto, c_apoyo, oscuro = PORTADAS[(variante + numero - 1) % len(PORTADAS)]
    rol, tiempo = ROLES[numero - 1]
    c = L.c
    L.fondo(fondo)
    if L.guias:  # la etiqueta con escena, rol y tiempo solo se ve en la vista previa
        L.bloque(f"ESCENA {numero} · {rol.upper()} · {tiempo}", NEGRITA, c_apoyo, M, ZONA_ARRIBA + 20,
                 W - 2 * M, 50, 34)
    # Espacio para la imagen o el video
    cierre = numero == len(CAMPOS)  # la última escena lleva los logos en vez de los nombres de las empresas
    y_caja, alto_caja = ZONA_ARRIBA + 110, 520 if cierre else 800
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
    if L.guias:
        c.setFont(NORMAL, 24)
        c.drawCentredString(W / 2, H - y_caja - alto_caja / 2 - 28, f"Escena {numero} · {tiempo}")
    # Texto en pantalla
    y_texto = y_caja + alto_caja + 60
    limite = 1180 if cierre else H - ZONA_ABAJO
    L.bloque(texto, MUY_NEGRITA, c_texto, M, y_texto, W - 2 * M, limite - y_texto, 96, inter=1.12)
    if cierre:
        _logos(L, oscuro, c_texto)


# En el logo de Constellation, la línea de base de la palabra CONSTELLATION está a esta fracción de su alto
# (medida sobre el SVG renderizado: el resto es «GLOBAL NETWORK», que no se usa para alinear).
LINEA_BASE_CONSTELLATION = 0.509


def _logos(L, oscuro: bool, c_texto: str) -> None:
    """Cierre: logo RC / FARÍAS al centro y, de pie de página, «Miembros de» + logo de Constellation en una línea.

    El texto comparte línea de base con la palabra CONSTELLATION (sin contar «GLOBAL NETWORK») y la línea
    baja hasta el borde inferior de la zona segura. Los logos usan la versión que contrasta con el fondo.
    """
    logos = marca()["logos"]
    L.c.drawImage(str(RAIZ / logos["fondo_oscuro" if oscuro else "fondo_claro_sobrio"]), M, H - 1330,
                  width=400, height=116, mask="auto", preserveAspectRatio=True)
    ruta = RAIZ / logos["constellation_blanco" if oscuro else "constellation_negro"]
    texto, tam, hueco, ancho_logo = "Miembros de", 37, 22, 360  # altura de mayúscula del texto ≈ alto de CONSTELLATION
    alto_logo = ancho_logo * tarjetas.proporcion_svg(str(ruta))
    borde = H - ZONA_ABAJO - 4                      # borde inferior del logo: límite de la zona segura (desde arriba)
    arriba = borde - alto_logo
    base = H - (arriba + LINEA_BASE_CONSTELLATION * alto_logo)  # línea de base común (desde abajo)
    ancho_texto = stringWidth(texto, NORMAL, tam)
    x0 = M - 3  # compensa el espacio lateral de la «M» para que su borde visible caiga en el margen
    L.c.setFillColor(L.col[c_texto])
    L.c.setFont(NORMAL, tam)
    L.c.drawString(x0, base, texto)
    L.logo_svg(ruta, x0 + ancho_texto + hueco + ancho_logo / 2, H - (arriba + alto_logo / 2), ancho_logo)


def generar_pdf(contenido: dict, titulo: str = "Reel", variante: int = 0, semilla: int = 0,
                guias: bool = False) -> bytes:
    """guias=True añade la etiqueta de cada escena (vista previa); False la omite (descarga)."""
    tarjetas._registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, tarjetas._colores(), alto=H, ancho=W, guias=guias)
    for i, campo in enumerate(CAMPOS, 1):
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante + semilla)
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    return tarjetas.nombre_archivo(contenido, mes_iso).replace("tarjetas-", "guion-visual-reel-", 1)
