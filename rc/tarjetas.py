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

# Solo las tarjetas 1 y 2 llevan ilustración 3D. Portada (1) y cierre (7) son fijos; la tarjeta 2 rota entre los
# estilos con ilustración y las tarjetas 3 y 4 entre los estilos solo de texto.
ESTILOS_TARJETA_2 = (2, 3, 4)
ESTILOS_SOLO_TEXTO = (5, 6, 8, 9)
ESTILOS_CON_ILUSTRACION = frozenset({1, 2, 3, 4})


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


TAM_MINIMO = 16  # suelo absoluto: el texto siempre debe caber completo, aunque la letra quede pequeña


def ajustar(texto, fuente, ancho, alto, tam_max, tam_min, inter):
    """Mayor tamaño de letra con el que el texto cabe entero (en alto y en ancho) en la caja dada.

    tam_min es el tamaño mínimo *deseado*; si aun así no cabe, se sigue achicando hasta TAM_MINIMO.
    """
    tam = tam_max
    while tam > TAM_MINIMO:
        lineas = envolver(texto, fuente, tam, ancho)
        cabe_alto = len(lineas) * tam * inter <= alto
        cabe_ancho = all(stringWidth(ln, fuente, tam) <= ancho for ln in lineas)
        if cabe_alto and cabe_ancho:
            return tam, lineas
        tam -= 2
    return TAM_MINIMO, envolver(texto, fuente, TAM_MINIMO, ancho)


class Lienzo:
    def __init__(self, c, col, alto=H, ancho=W):
        self.c, self.col, self.alto, self.ancho = c, col, alto, ancho

    def bloque(self, texto, fuente, color, x, y_sup, ancho, alto, tam_max, alinear="izq", inter=1.2, tam_min=34):
        """Texto con el borde superior en y_sup (medido desde arriba). Devuelve el alto usado."""
        if not (texto or "").strip():
            return 0
        c = self.c
        tam, lineas = ajustar(texto, fuente, ancho, alto, tam_max, tam_min, inter)
        c.setFillColor(self.col[color])
        c.setFont(fuente, tam)
        y = self.alto - y_sup - tam * 0.95
        for ln in lineas:
            w = stringWidth(ln, fuente, tam)
            px = x if alinear == "izq" else (x + ancho - w if alinear == "der" else x + (ancho - w) / 2)
            c.drawString(px, y, ln)
            y -= tam * inter
        return len(lineas) * tam * inter

    def fondo(self, color):
        self.c.setFillColor(self.col[color])
        self.c.rect(0, 0, self.ancho, self.alto, stroke=0, fill=1)

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
        tam, lineas = ajustar(nota or "", NORMAL, ancho - 120, alto / 2 - 50, 22, 14, 1.35)
        c.setFont(NORMAL, tam)
        for i, ln in enumerate(lineas):
            c.drawCentredString(x + ancho / 2, y + alto / 2 - 14 - i * tam * 1.35, ln)

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

# Portadas: el color de fondo rota para que el feed se vea variado (fondo, titular, texto, ilustración sobre fondo oscuro)
PORTADAS = (
    ("coral", "blanco", "blanco", True),
    ("celeste", "azul_marino", "azul_marino", False),
    ("azul_medio", "blanco", "celeste", True),
    ("gris_claro", "azul_marino", "coral", False),
    ("azul_marino", "blanco", "celeste", True),
)


def estilo1_portada(L, d):
    """Fondo que rota (coral, celeste, azul, gris, marino) · ilustración arriba · titular grande abajo."""
    fondo, c_titular, c_texto, oscuro = PORTADAS[d.get("variante", 0) % len(PORTADAS)]
    L.fondo(fondo)
    L.marcador(M, 84, W - 2 * M, 640, d["nota"], claro=oscuro)
    usado = L.bloque(d["titular"], MUY_NEGRITA, c_titular, M, 780, W - 2 * M, 380, 124, tam_min=64, inter=1.08)
    y = 780 + usado + 24
    L.bloque(d["texto"], NORMAL, c_texto, M, y, W - 2 * M, H - 70 - y, 52)


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
    u = L.bloque(d["titular"], NEGRITA, "coral", 520, 190, W - 520 - M, 420, 80, alinear="der", tam_min=44, inter=1.15)
    L.bloque(d["texto"], NORMAL, "coral", 520, 190 + u + 60, W - 520 - M, 880 - u - 60, 50, alinear="der", tam_min=32)


def estilo5_gris_pildora(L, d):
    """Gris · titular en negrita arriba · '+' coral y texto azul marino debajo (sin píldora)."""
    c = L.c
    L.fondo("gris_claro")
    u = L.bloque(d["titular"], NEGRITA, "azul_marino", M, 150, W - 2 * M, 520, 84, inter=1.15)
    y_texto = 150 + u + 90
    cx, cy = M + 115, H - y_texto - 70  # centro del "+"
    c.setFillColor(L.col["coral"])
    c.rect(cx - 95, cy - 17, 190, 34, stroke=0, fill=1)
    c.rect(cx - 17, cy - 95, 34, 190, stroke=0, fill=1)
    L.bloque(d["texto"], NORMAL, "azul_marino", 330, y_texto, W - 330 - M, H - 90 - y_texto, 60)


def estilo6_celeste(L, d):
    """Celeste · flecha + titular · texto de apoyo."""
    L.fondo("celeste")
    L.flecha(M, 250, 0.9)
    u = L.bloque(d["titular"], MUY_NEGRITA, "azul_marino", M + 190, 190, W - M - (M + 190), 330, 80, tam_min=48, inter=1.1)
    y = 190 + max(u, 100) + 70
    L.bloque(d["texto"], NORMAL, "azul_marino", M, y, W - 2 * M, 1340 - y, 58, tam_min=34, inter=1.25)


def estilo8_marino_texto(L, d):
    """Azul marino · flecha coral · titular blanco en negrita · texto celeste (sin ilustración)."""
    L.fondo("azul_marino")
    L.flecha(M, 230, 0.9)
    u = L.bloque(d["titular"], MUY_NEGRITA, "blanco", M, 300, W - 2 * M, 520, 88, tam_min=44, inter=1.12)
    L.c.setFillColor(L.col["coral"])
    L.c.rect(M, H - (300 + u + 50) - 8, 220, 8, stroke=0, fill=1)
    y = 300 + u + 90
    L.bloque(d["texto"], NORMAL, "celeste", M, y, W - 2 * M, H - 90 - y, 58, inter=1.25)


def estilo9_blanco_texto(L, d):
    """Blanco · titular coral en negrita · texto azul marino · barra celeste (sin ilustración)."""
    L.fondo("blanco")
    L.c.setFillColor(L.col["celeste"])
    L.c.rect(0, H - 40, W, 40, stroke=0, fill=1)
    u = L.bloque(d["titular"], MUY_NEGRITA, "coral", M, 200, W - 2 * M, 560, 92, tam_min=44, inter=1.12)
    y = 200 + u + 70
    L.bloque(d["texto"], NORMAL, "azul_marino", M, y, W - 2 * M, H - 90 - y, 58, inter=1.25)


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
           5: estilo5_gris_pildora, 6: estilo6_celeste, 7: estilo7_cierre,
           8: estilo8_marino_texto, 9: estilo9_blanco_texto}
NOMBRES = {1: "Portada", 2: "Azul marino", 3: "Coral partido", 4: "Blanco lateral",
           5: "Gris con titular", 6: "Celeste", 7: "Cierre", 8: "Azul marino texto", 9: "Blanco texto"}


# ---------- datos de cada tarjeta ----------

CAMPOS_SLIDE = ("slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre")


def _separar(texto: str) -> tuple[str, str]:
    """Titular + resto para contenidos viejos sin `diseno`: la primera oración (o hasta los dos puntos).

    Solo corta en un límite natural; si el texto es una sola oración, todo va como titular, porque
    partir una frase a la mitad deja un titular sin sentido.
    """
    texto = (texto or "").strip()
    partes = re.split(r"(?<=[:.?!])\s+", texto, maxsplit=1)
    if len(partes) == 2 and 0 < len(partes[0].split()) <= 30:
        return partes[0].rstrip(":."), partes[1]
    return texto, ""


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
    """Portada · tarjeta 2 con ilustración · tarjetas 3 y 4 solo texto · cierre. Rotan según la variante."""
    n = len(ESTILOS_SOLO_TEXTO)
    return [1, ESTILOS_TARJETA_2[variante % len(ESTILOS_TARJETA_2)],
            ESTILOS_SOLO_TEXTO[(variante * 2) % n], ESTILOS_SOLO_TEXTO[(variante * 2 + 1) % n], 7]


def generar_pdf(contenido: dict, titulo: str = "Carrusel", variante: int = 0) -> bytes:
    _registrar_fuentes()
    col = _colores()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, col)
    for estilo, datos in zip(estilos_sugeridos(variante), datos_tarjetas(contenido)):
        ESTILOS[estilo](L, {**datos, "variante": variante})
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    tema = re.sub(r"[^a-z0-9]+", "-", (contenido.get("tema_especifico") or "carrusel").lower().encode("ascii", "ignore").decode()).strip("-")[:40]
    return f"tarjetas-{mes_iso[:7]}-{tema or 'carrusel'}.pdf"


def imagenes_png(pdf: bytes, ancho: int = 720) -> list[bytes]:
    """Una imagen PNG por tarjeta (para la vista previa en pantalla)."""
    import pymupdf  # import diferido: solo se usa en la vista previa
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return [pagina.get_pixmap(matrix=pymupdf.Matrix(ancho / W, ancho / W)).tobytes("png") for pagina in doc]
