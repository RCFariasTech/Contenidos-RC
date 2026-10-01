"""Tarjetas de carrusel 3:4 (1080 x 1440) en PDF vectorial para el equipo de diseño.

Texto vivo y formas vectoriales (editable en Illustrator). Las ilustraciones 3D se hacen en Krea:
aquí solo se reserva el espacio con la nota de qué ilustrar. Colores desde config/marca.json.
"""

import io
import re
from functools import lru_cache
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from rc.config import RAIZ, marca

W, H, M = 1080, 1440, 84
NEGRITA, MUY_NEGRITA, NORMAL = "Mont-Bold", "Mont-Black", "Mont-Regular"

# Estilos 1 (portada) y 7 (cierre) son fijos; las tarjetas intermedias rotan entre estos.
ESTILOS_INTERMEDIOS = (2, 3, 4, 5, 6)


@lru_cache(maxsize=1)
def _registrar_fuentes() -> None:
    for nombre in ("Black", "Bold", "Regular"):
        pdfmetrics.registerFont(TTFont(f"Mont-{nombre}", str(RAIZ / "plantilla" / "fuentes" / f"Montserrat-{nombre}.ttf")))


def _colores() -> dict:
    p = marca()["paleta"]
    return {k: HexColor(p[k]) for k in ("coral", "celeste", "azul_medio", "gris_claro", "azul_marino", "blanco")}


# ---------- texto ----------

def envolver(texto, fuente, tam, ancho):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if stringWidth(prueba, fuente, tam) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def ajustar(texto, fuente, ancho, alto, tam_max, tam_min, inter):
    """Mayor tamaño (entre tam_max y tam_min) con el que el texto cabe en el alto dado."""
    tam = tam_max
    while tam > tam_min:
        lineas = envolver(texto, fuente, tam, ancho)
        if len(lineas) * tam * inter <= alto:
            return tam, lineas
        tam -= 2
    return tam_min, envolver(texto, fuente, tam_min, ancho)


class Lienzo:
    def __init__(self, c, col):
        self.c, self.col = c, col

    def bloque(self, texto, fuente, color, x, y_sup, ancho, alto, tam_max, alinear="izq", inter=1.2, tam_min=34):
        """Texto con el borde superior en y_sup (medido desde arriba). Devuelve el alto usado."""
        if not (texto or "").strip():
            return 0
        c = self.c
        tam, lineas = ajustar(texto, fuente, ancho, alto, tam_max, tam_min, inter)
        c.setFillColor(self.col[color])
        c.setFont(fuente, tam)
        y = H - y_sup - tam * 0.95
        for ln in lineas:
            w = stringWidth(ln, fuente, tam)
            px = x if alinear == "izq" else (x + ancho - w if alinear == "der" else x + (ancho - w) / 2)
            c.drawString(px, y, ln)
            y -= tam * inter
        return len(lineas) * tam * inter

    def fondo(self, color):
        self.c.setFillColor(self.col[color])
        self.c.rect(0, 0, W, H, stroke=0, fill=1)

    def marcador(self, x, y_sup, ancho, alto, nota, claro=True):
        """Espacio reservado para la ilustración 3D de Krea, con la nota de qué ilustrar."""
        c = self.c
        y = H - y_sup - alto
        tinta = self.col["blanco"] if claro else self.col["azul_marino"]
        c.saveState()
        c.setFillColor(tinta)
        c.setFillAlpha(0.14 if claro else 0.10)
        c.setStrokeColor(tinta)
        c.setStrokeAlpha(0.75)
        c.setLineWidth(3)
        c.setDash(14, 10)
        c.roundRect(x, y, ancho, alto, 36, stroke=1, fill=1)
        c.restoreState()
        c.setFillColor(tinta)
        c.setFont(NEGRITA, 28)
        c.drawCentredString(x + ancho / 2, y + alto / 2 + 30, "ILUSTRACIÓN 3D · Krea")
        c.setFont(NORMAL, 22)
        for i, ln in enumerate(envolver(nota or "", NORMAL, 22, ancho - 120)[:6]):
            c.drawCentredString(x + ancho / 2, y + alto / 2 - 14 - i * 30, ln)

    def flecha(self, x, y_sup, escala=1.0):
        """Punto + flecha coral de las tarjetas publicadas."""
        c = self.c
        y = H - y_sup
        c.setFillColor(self.col["coral"])
        c.circle(x + 14 * escala, y, 14 * escala, stroke=0, fill=1)
        c.setStrokeColor(self.col["coral"])
        c.setLineWidth(22 * escala)
        c.setLineCap(1)
        c.setLineJoin(1)
        c.line(x + 62 * escala, y, x + 150 * escala, y)
        p = c.beginPath()
        p.moveTo(x + 118 * escala, y + 44 * escala)
        p.lineTo(x + 160 * escala, y)
        p.lineTo(x + 118 * escala, y - 44 * escala)
        c.drawPath(p, stroke=1, fill=0)

    def logo_svg(self, ruta, cx, cy, ancho):
        """SVG como vector, centrado en (cx, cy) (cy medido desde abajo)."""
        from svglib.svglib import svg2rlg  # import diferido: solo al generar tarjetas
        dib = svg2rlg(str(ruta))
        k = ancho / dib.width
        dib.scale(k, k)
        renderPDF.draw(dib, self.c, cx - ancho / 2, cy - dib.height * k / 2)


# ---------- los 7 estilos (todos reciben titular, texto y nota de ilustración) ----------

def estilo1_portada(L, d):
    """Coral · ilustración arriba · titular grande abajo."""
    L.fondo("coral")
    L.marcador(M, 84, W - 2 * M, 640, d["nota"])
    usado = L.bloque(d["titular"], MUY_NEGRITA, "blanco", M, 780, W - 2 * M, 440, 124, tam_min=64, inter=1.08)
    L.bloque(d["texto"], NORMAL, "blanco", M, 780 + usado + 24, W - 2 * M, 200, 52)


def estilo2_navy_centro(L, d):
    """Azul marino · flecha · ilustración al centro · titular y remate abajo."""
    L.fondo("azul_marino")
    L.flecha(W / 2 - 80, 190, 1.0)
    L.marcador(M + 100, 330, W - 2 * M - 200, 560, d["nota"])
    L.c.setFillColor(L.col["coral"])
    L.c.rect(M + 130, H - 920, W - 2 * M - 260, 8, stroke=0, fill=1)
    u = L.bloque(d["titular"], NEGRITA, "blanco", M, 980, W - 2 * M, 190, 66, alinear="centro", tam_min=40)
    L.bloque(d["texto"], NORMAL, "celeste", M, 980 + u + 16, W - 2 * M, 1360 - (980 + u + 16), 50, alinear="centro", tam_min=32)


def estilo3_coral_partido(L, d):
    """Coral · titular enorme arriba · ilustración a la izquierda · texto a la derecha."""
    L.fondo("coral")
    L.bloque(d["titular"], MUY_NEGRITA, "blanco", M, 90, W - 2 * M, 470, 104, tam_min=60, inter=1.1)
    L.marcador(M, 620, 420, 620, d["nota"])
    L.bloque(d["texto"], NORMAL, "blanco", 540, 620, W - 540 - M, 620, 54, alinear="der", tam_min=32)


def estilo4_blanco_lateral(L, d):
    """Blanco · ilustración a la izquierda · texto coral alineado a la derecha."""
    L.fondo("blanco")
    L.marcador(M, 190, 410, 880, d["nota"], claro=False)
    u = L.bloque(d["titular"], NEGRITA, "coral", 520, 190, W - 520 - M, 560, 80, alinear="der", tam_min=44, inter=1.15)
    L.bloque(d["texto"], NORMAL, "coral", 520, 190 + u + 60, W - 520 - M, 880 - u - 60, 50, alinear="der", tam_min=32)


def estilo5_gris_pildora(L, d):
    """Gris · '+' coral · texto azul marino · píldora coral con el titular (dato)."""
    c = L.c
    L.fondo("gris_claro")
    c.setFillColor(L.col["coral"])
    c.rect(M + 20, H - 590, 190, 34, stroke=0, fill=1)
    c.rect(M + 98, H - 668, 34, 190, stroke=0, fill=1)
    L.bloque(d["texto"], NORMAL, "azul_marino", 330, 200, W - 330 - M, 680, 60)
    ancho, alto = W - 2 * M, 280
    c.setFillColor(L.col["coral"])
    c.roundRect(M, H - 1200, ancho, alto, 140, stroke=0, fill=1)
    tam, lineas = ajustar(d["titular"], NEGRITA, ancho - 140, 190, 74, 40, 1.15)
    L.bloque(d["titular"], NEGRITA, "blanco", M + 70, 920 + (alto - len(lineas) * tam * 1.15) / 2 - 4,
             ancho - 140, 190, 74, alinear="centro", tam_min=40, inter=1.15)


def estilo6_celeste(L, d):
    """Celeste · flecha + titular · texto de apoyo."""
    L.fondo("celeste")
    L.flecha(M, 250, 0.9)
    u = L.bloque(d["titular"], MUY_NEGRITA, "azul_marino", M + 190, 190, W - M - (M + 190), 330, 80, tam_min=48, inter=1.1)
    y = 190 + max(u, 100) + 70
    L.bloque(d["texto"], NORMAL, "azul_marino", M, y, W - 2 * M, 1340 - y, 58, tam_min=34, inter=1.25)


def estilo7_cierre(L, d):
    """Blanco · marco con Constellation arriba · cita centrada · logo RC / FARÍAS abajo."""
    c = L.c
    L.fondo("blanco")
    c.setStrokeColor(L.col["azul_marino"])
    c.setLineWidth(3)
    x0, y0, x1, y1 = 56, H - 1190, W - 56, H - 214
    c.roundRect(x0, y0, x1 - x0, y1 - y0, 40, stroke=1, fill=0)
    c.setFillColor(L.col["blanco"])
    c.rect(x0 + 110, y1 - 8, x1 - x0 - 220, 18, stroke=0, fill=1)
    c.rect(x0 + 160, y0 - 6, x1 - x0 - 320, 14, stroke=0, fill=1)
    L.logo_svg(RAIZ / marca()["logos"]["constellation_negro"], W / 2, y1 - 2, 600)
    texto = " ".join(p for p in (d["titular"], d["texto"]) if p).strip()
    L.bloque(f"“{texto}”", NORMAL, "azul_marino", 130, 400, W - 260, 560, 58, alinear="centro", tam_min=36, inter=1.28)
    c.drawImage(str(RAIZ / marca()["logos"]["fondo_claro_sobrio"]), W / 2 - 215, y0 - 52,
                width=430, height=125, mask="auto", preserveAspectRatio=True)


ESTILOS = {1: estilo1_portada, 2: estilo2_navy_centro, 3: estilo3_coral_partido, 4: estilo4_blanco_lateral,
           5: estilo5_gris_pildora, 6: estilo6_celeste, 7: estilo7_cierre}
NOMBRES = {1: "Portada", 2: "Azul marino", 3: "Coral partido", 4: "Blanco lateral",
           5: "Gris con píldora", 6: "Celeste", 7: "Cierre"}


# ---------- datos de cada tarjeta ----------

CAMPOS_SLIDE = ("slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre")


def _separar(texto: str) -> tuple[str, str]:
    """Titular + resto para contenidos viejos sin `diseno`: primera frase corta, o las primeras palabras."""
    partes = re.split(r"(?<=[:.])\s+", (texto or "").strip(), maxsplit=1)
    if len(partes) == 2 and len(partes[0].split()) <= 9:
        return partes[0].rstrip(":."), partes[1]
    palabras = (texto or "").split()
    return " ".join(palabras[:5]), " ".join(palabras[5:])


def datos_tarjetas(contenido: dict) -> list[dict]:
    """Las 5 tarjetas con titular, texto y nota de ilustración (usa `diseno` si existe)."""
    diseno = contenido.get("diseno") or []
    tarjetas = []
    for i, campo in enumerate(CAMPOS_SLIDE):
        texto = contenido.get(campo, "")
        if i < len(diseno):
            d = diseno[i]
            tarjetas.append({"titular": d.get("titular", ""), "texto": d.get("texto", ""),
                             "nota": d.get("ilustracion", "")})
        elif i == 0:
            tarjetas.append({"titular": texto, "texto": "", "nota": ""})
        elif i == len(CAMPOS_SLIDE) - 1:
            tarjetas.append({"titular": "", "texto": texto, "nota": ""})
        else:
            titular, resto = _separar(texto)
            tarjetas.append({"titular": titular, "texto": resto, "nota": ""})
    return tarjetas


def estilos_sugeridos(variante: int = 0) -> list[int]:
    """Portada, 3 estilos intermedios que rotan según la variante (0, 1, …) y cierre."""
    n = len(ESTILOS_INTERMEDIOS)
    return [1, *(ESTILOS_INTERMEDIOS[(variante * 3 + i) % n] for i in range(3)), 7]


def generar_pdf(contenido: dict, titulo: str = "Carrusel", variante: int = 0) -> bytes:
    _registrar_fuentes()
    col = _colores()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, col)
    for estilo, datos in zip(estilos_sugeridos(variante), datos_tarjetas(contenido)):
        ESTILOS[estilo](L, datos)
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    tema = re.sub(r"[^a-z0-9]+", "-", (contenido.get("tema_especifico") or "carrusel").lower().encode("ascii", "ignore").decode()).strip("-")[:40]
    return f"tarjetas-{mes_iso[:7]}-{tema or 'carrusel'}.pdf"
