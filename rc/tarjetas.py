"""Tarjetas de carrusel 4:5 (1080 x 1350) en PDF vectorial · sistema gráfico RC Farías 2026.

Orden fijo de 5 plantillas (guía visual 2026):
  1. Gancho  · azul marino, titular gigante en Space Grotesk Bold gris + ícono isométrico (Krea).
  2. Foto    · azul, texto arriba y foto real (Krea, Nano Banana Pro) con velo azul abajo.
  3. Ícono   · gris, ícono de línea de la guía (marino + rojo) y texto marino.
  4. Dato    · rojo, cifra gigante en Space Grotesk Bold entre dos líneas de texto. Si la tarjeta no
               tiene cifra, se usa otra vez la plantilla de ícono.
  5. Cierre  · azul marino, comillas rojas, texto blanco y logos RC Farías + Constellation.

Texto vivo y formas vectoriales (editable en Illustrator). Colores desde config/marca.json («paleta_2026»).
"""

import io
import re
from functools import lru_cache
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from rc.config import RAIZ, marca

W, H, M = 1080, 1350, 96
TITULO, TITULO_MEDIO, TEXTO, TEXTO_SEMI = "SpaceGrotesk-Bold", "SpaceGrotesk-Medium", "Sora-Regular", "Sora-SemiBold"
PLANTILLA = RAIZ / "plantilla"
DIR_ICONOS = PLANTILLA / "iconos_linea"

NOMBRES = {1: "Gancho", 2: "Foto", 3: "Ícono", 4: "Dato", 5: "Cierre"}
# Tarjetas que llevan imagen de Krea, qué tipo y su caja (ancho, alto) en px.
TIPO_IMAGEN = {1: "icono", 2: "foto", 3: "linea"}
AREA_IMAGEN = {1: (500, 500), 2: (W, 620), 3: (260, 260)}
PROPORCION_KREA = {1: "1:1", 2: "16:9", 3: "1:1"}

PALETA_2026 = {"marino": "#12244A", "rojo": "#FF0006", "rojo2": "#FF1F35", "azul": "#005EFF",
               "gris": "#C9CACB", "gris_claro": "#E8E8E8", "blanco": "#FFFFFF", "negro": "#171719"}

RE_CIFRA = re.compile(r"[+\-]?(?:US\$|\$)?\d+(?:[.,]\d+)*\s?(?:%|x\b)?")


@lru_cache(maxsize=1)
def _registrar_fuentes() -> None:
    for nombre in (TITULO, TITULO_MEDIO, TEXTO, TEXTO_SEMI):
        pdfmetrics.registerFont(TTFont(nombre, str(PLANTILLA / "fuentes" / f"{nombre}.ttf")))


def _colores() -> dict:
    p = {**PALETA_2026, **(marca().get("paleta_2026") or {})}
    return {k: HexColor(v) for k, v in p.items()}


@lru_cache(maxsize=1)
def iconos_linea() -> tuple[str, ...]:
    """Claves de los íconos de línea disponibles (nombre del archivo sin .svg)."""
    return tuple(sorted(p.stem for p in DIR_ICONOS.glob("*.svg")))


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


def ajustar(texto, fuente, ancho, alto, tam_max, inter):
    """Mayor tamaño de letra con el que el texto cabe entero (en alto y en ancho) en la caja dada."""
    tam = tam_max
    while tam > TAM_MINIMO:
        lineas = envolver(texto, fuente, tam, ancho)
        if len(lineas) * tam * inter <= alto and all(stringWidth(ln, fuente, tam) <= ancho for ln in lineas):
            return tam, lineas
        tam -= 2
    return TAM_MINIMO, envolver(texto, fuente, TAM_MINIMO, ancho)


# ---------- imágenes ----------

def _abrir(datos: bytes, alfa: bool = False):
    from PIL import Image
    img = Image.open(io.BytesIO(datos))
    if alfa and (img.mode in ("RGBA", "LA") or "transparency" in img.info):
        return img.convert("RGBA")
    return img.convert("RGB")


def color_fondo_imagen(datos: bytes) -> str:
    """Hex del fondo real de la imagen (mediana de su borde). La tarjeta 1 se pinta con este color para que el ícono
    y el fondo sean el mismo tono (Krea nunca clava exactamente el color pedido)."""
    img = _abrir(datos)
    img.thumbnail((200, 200))
    w, h = img.size
    borde = [img.getpixel((x, y)) for x in range(0, w, 4) for y in (0, 1, h - 2, h - 1)]
    borde += [img.getpixel((x, y)) for y in range(0, h, 4) for x in (0, 1, w - 2, w - 1)]
    return "#" + "".join(f"{sorted(c[i] for c in borde)[len(borde) // 2]:02X}" for i in range(3))


def _parecido(hex_a: str, hex_b: str, tolerancia: int = 40) -> bool:
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return sum(abs(x - y) for x, y in zip(a, b)) <= tolerancia * 3


def recortar(datos: bytes, ancho: float, alto: float, escala: float = 1.5, borde_suave: bool = False) -> bytes:
    """La imagen recortada (tipo «cover») a la proporción de la caja. borde_suave difumina apenas el contorno."""
    from PIL import Image, ImageDraw, ImageFilter
    img = _abrir(datos, alfa=True)
    w, h = max(1, round(ancho * escala)), max(1, round(alto * escala))
    if img.mode == "RGBA":  # PNG con transparencia: se encaja entero, sin recortar ni difuminar
        img.thumbnail((w, h), Image.LANCZOS)
        salida = io.BytesIO()
        img.save(salida, "PNG", optimize=True)
        return salida.getvalue()
    k = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * k)), max(h, round(img.height * k))), Image.LANCZOS)
    izq, arr = (img.width - w) // 2, (img.height - h) // 2
    img = img.crop((izq, arr, izq + w, arr + h))
    if borde_suave:
        borde = max(2, round(min(w, h) * 0.04))
        mascara = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mascara).rectangle((borde, borde, w - borde - 1, h - borde - 1), fill=255)
        img.putalpha(mascara.filter(ImageFilter.GaussianBlur(borde / 2)))
    salida = io.BytesIO()
    img.save(salida, "PNG" if borde_suave else "JPEG", **({"optimize": True} if borde_suave else {"quality": 90}))
    return salida.getvalue()


# ---------- lienzo ----------

class Lienzo:
    def __init__(self, c, col, guias=True, imagenes=None):
        # guias=False (PDF que se descarga): se omiten los recuadros y notas que solo sirven en la vista previa.
        # imagenes: {tarjeta: bytes} con la imagen elegida en Krea (1: ícono isométrico, 2: foto).
        self.c, self.col, self.guias, self.imagenes, self.tarjeta = c, col, guias, imagenes or {}, 0

    def fondo(self, color):
        self.c.setFillColor(self.col[color] if color in self.col else HexColor(color))
        self.c.rect(0, 0, W, H, stroke=0, fill=1)

    def bloque(self, texto, fuente, color, x, y_sup, ancho, alto, tam_max, inter=1.25):
        """Texto con el borde superior en y_sup (desde arriba). Devuelve el alto usado."""
        if not (texto or "").strip():
            return 0
        tam, lineas = ajustar(texto, fuente, ancho, alto, tam_max, inter)
        self.c.setFillColor(self.col[color])
        self.c.setFont(fuente, tam)
        y = H - y_sup - tam * 0.9
        for ln in lineas:
            self.c.drawString(x, y, ln)
            y -= tam * inter
        return len(lineas) * tam * inter

    def svg(self, ruta, x, y_sup, ancho):
        from svglib.svglib import svg2rlg  # import diferido: solo al generar tarjetas
        dib = svg2rlg(str(ruta))
        k = ancho / dib.width
        dib.scale(k, k)
        renderPDF.draw(dib, self.c, x, H - y_sup - dib.height * k)
        return dib.height * k

    def png(self, ruta_o_bytes, x, y_sup, ancho, alto):
        fuente = io.BytesIO(ruta_o_bytes) if isinstance(ruta_o_bytes, bytes) else str(ruta_o_bytes)
        self.c.drawImage(ImageReader(fuente), x, H - y_sup - alto, ancho, alto, mask="auto",
                         preserveAspectRatio=True, anchor="sw")

    def recuadro_guia(self, x, y_sup, ancho, alto, rotulo, nota, tinta="blanco"):
        """En la vista previa: recuadro punteado con qué imagen va y la nota de qué mostrar."""
        if not self.guias:
            return
        c, y = self.c, H - y_sup - alto
        c.saveState()
        c.setFillColor(self.col[tinta])
        c.setFillAlpha(0.12)
        c.setStrokeColor(self.col[tinta])
        c.setStrokeAlpha(0.7)
        c.setLineWidth(3)
        c.setDash(14, 10)
        c.roundRect(x, y, ancho, alto, 28, stroke=1, fill=1)
        c.restoreState()
        c.setFillColor(self.col[tinta])
        c.setFont(TEXTO_SEMI, 26)
        c.drawCentredString(x + ancho / 2, y + alto / 2 + 24, rotulo)
        tam, lineas = ajustar(nota or "", TEXTO, ancho - 100, alto / 2 - 40, 20, 1.35)
        c.setFont(TEXTO, tam)
        for i, ln in enumerate(lineas):
            c.drawCentredString(x + ancho / 2, y + alto / 2 - 16 - i * tam * 1.35, ln)


# ---------- las 5 plantillas ----------

def t1_gancho(L, d):
    datos = L.imagenes.get(1)
    fondo = L.col["marino"]
    if datos:
        try:
            real = color_fondo_imagen(datos) if _abrir(datos, alfa=True).mode == "RGB" else PALETA_2026["marino"]
            if _parecido(real, PALETA_2026["marino"]):
                fondo = HexColor(real)
        except Exception:
            datos = None
    L.c.setFillColor(fondo)
    L.c.rect(0, 0, W, H, stroke=0, fill=1)
    usado = L.bloque(d["titular"], TITULO, "gris", M, 120, W - 2 * M, 600, 150, inter=1.0)
    if d.get("texto"):
        L.bloque(d["texto"], TEXTO, "blanco", M, 150 + usado, 620, 200, 40)
    ancho, alto = AREA_IMAGEN[1]
    x, y_sup = W - M - ancho + 40, H - alto - 80
    if datos:
        try:
            L.png(recortar(datos, ancho, alto, borde_suave=True), x, y_sup, ancho, alto)
            return
        except Exception:
            pass
    L.recuadro_guia(x, y_sup, ancho, alto, "ÍCONO ISOMÉTRICO · Krea", d.get("nota", ""))


def t2_foto(L, d):
    L.fondo("azul")
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    ancho, alto = AREA_IMAGEN[2]
    L.bloque(texto, TEXTO, "blanco", M, 110, W - 2 * M - 40, H - alto - 180, 50, inter=1.3)
    datos = L.imagenes.get(2)
    if datos:
        try:
            L.png(recortar(datos, ancho, alto), 0, H - alto, ancho, alto)
            L.c.saveState()
            L.c.setFillColor(L.col["azul"])
            L.c.setFillAlpha(0.45)
            L.c.rect(0, 0, ancho, alto, stroke=0, fill=1)
            L.c.restoreState()
            return
        except Exception:
            pass
    L.recuadro_guia(M, H - alto + 20, W - 2 * M, alto - 100, "FOTO · Krea (con velo azul)", d.get("nota", ""))


def _icono_de(d: dict, alternativa: int) -> str:
    claves = iconos_linea()
    pedido = (d.get("icono") or "").strip().lower()
    return pedido if pedido in claves else claves[alternativa % len(claves)]


def t3_icono(L, d):
    # La imagen de Krea (ícono de línea generado) solo aplica a la tarjeta 3; la 4 sin cifra usa el ícono de la guía.
    datos = L.imagenes.get(3) if L.tarjeta == 3 else None
    fondo = L.col["gris"]
    if datos:
        try:
            real = color_fondo_imagen(datos)
            if _parecido(real, PALETA_2026["gris"]):
                fondo = HexColor(real)
        except Exception:
            datos = None
    L.c.setFillColor(fondo)
    L.c.rect(0, 0, W, H, stroke=0, fill=1)
    ancho, alto = AREA_IMAGEN[3]
    puesto = False
    if datos:
        try:
            L.png(recortar(datos, ancho, alto, borde_suave=True), M - 40, 110, ancho, alto)
            puesto = True
        except Exception:
            pass
    if not puesto:
        L.svg(DIR_ICONOS / f"{_icono_de(d, d.get('alternativa', 0))}.svg", M, 150, 180)
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    L.bloque(texto, TEXTO, "marino", M, 520, W - 2 * M - 60, H - 520 - M, 54, inter=1.3)


def separar_cifra(texto: str) -> tuple[str, str, str]:
    """(antes, cifra, después) con la primera cifra del texto; cifra vacía si no hay."""
    m = RE_CIFRA.search(texto or "")
    if not m or not re.search(r"\d", m.group(0)):
        return texto, "", ""
    return texto[:m.start()].strip(), m.group(0).strip(), texto[m.end():].strip()


def t4_dato(L, d):
    todo = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    antes, cifra, despues = separar_cifra(todo)
    L.fondo("rojo2")
    usado = L.bloque(antes, TEXTO, "blanco", M, 120, W - 2 * M - 60, 340, 46, inter=1.3)
    y = 120 + usado + 30
    tam = 300
    while tam > 120 and stringWidth(cifra, TITULO, tam) > W - 2 * M:
        tam -= 10
    L.c.setFillColor(L.col["gris"])
    L.c.setFont(TITULO, tam)
    L.c.drawString(M - tam * 0.04, H - y - tam * 0.86, cifra)
    y += tam * 0.86 + 60
    L.bloque(despues, TEXTO, "blanco", M, y, W - 2 * M - 60, H - y - M, 46, inter=1.3)


def t5_cierre(L, d):
    L.fondo("marino")
    L.c.setFillColor(L.col["rojo"])
    L.c.setFont(TITULO, 520)
    L.c.drawString(W - M - 300, H - 520, "”")
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    L.bloque(texto, TEXTO, "blanco", M, 330, 680, 640, 50, inter=1.3)
    L.png(PLANTILLA / "logo_rc_blanco_2026.png", M, H - 175, 300, 80)
    L.svg(PLANTILLA / "logo_constellation_blanco.svg", W - M - 330, H - 160, 330)


PLANTILLAS = {1: t1_gancho, 2: t2_foto, 3: t3_icono, 4: t4_dato, 5: t5_cierre}


# ---------- datos de cada tarjeta ----------

CAMPOS_SLIDE = ("slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre")


def _separar(texto: str) -> tuple[str, str]:
    """Titular + resto para contenidos viejos sin `diseno`: la primera oración (o hasta los dos puntos)."""
    texto = (texto or "").strip()
    partes = re.split(r"(?<=[:.?!])\s+", texto, maxsplit=1)
    if len(partes) == 2 and 0 < len(partes[0].split()) <= 30:
        return partes[0].rstrip(":."), partes[1]
    return texto, ""


def datos_tarjetas(contenido: dict) -> list[dict]:
    """Las 5 tarjetas con titular, texto, nota de imagen y (tarjeta 3) clave del ícono de línea."""
    diseno = contenido.get("diseno") or []
    tarjetas = []
    for i, campo in enumerate(CAMPOS_SLIDE):
        texto = contenido.get(campo, "")
        if i < len(diseno):
            d = diseno[i]
            tarjetas.append({"titular": d.get("titular", ""), "texto": d.get("texto", ""),
                             "nota": d.get("ilustracion", ""), "icono": d.get("icono", "")})
        elif i == 0:
            tarjetas.append({"titular": texto, "texto": "", "nota": "", "icono": ""})
        elif i == len(CAMPOS_SLIDE) - 1:
            tarjetas.append({"titular": "", "texto": texto, "nota": "", "icono": ""})
        else:
            titular, resto = _separar(texto)
            tarjetas.append({"titular": titular, "texto": resto, "nota": "", "icono": ""})
    for t, campo in zip(tarjetas, CAMPOS_SLIDE):
        t["completo"] = " ".join((contenido.get(campo) or "").split()) or " ".join(p for p in (t["titular"], t["texto"]) if p)
    return tarjetas


def plantillas_de(contenido: dict) -> list[int]:
    """Plantilla de cada tarjeta: orden fijo; la 4 pasa a «ícono» si no tiene cifra."""
    t4 = datos_tarjetas(contenido)[3]
    tiene_cifra = bool(separar_cifra(t4["completo"])[1])
    return [1, 2, 3, 4 if tiene_cifra else 3, 5]


def generar_pdf(contenido: dict, titulo: str = "Carrusel", variante: int = 0, semilla: int = 0,
                guias: bool = False, imagenes: dict[int, bytes] | None = None) -> bytes:
    """guias=True dibuja los recuadros de imagen con su nota (vista previa); False los omite (descarga).

    variante + semilla solo cambian el ícono de línea cuando la tarjeta no pidió uno («Rehacer tarjetas»).
    """
    _registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, _colores(), guias=guias, imagenes=imagenes)
    for numero, (plantilla, datos) in enumerate(zip(plantillas_de(contenido), datos_tarjetas(contenido)), 1):
        L.tarjeta = numero
        PLANTILLAS[plantilla](L, {**datos, "alternativa": variante + semilla * 3 + numero * 5})
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
