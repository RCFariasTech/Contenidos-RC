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
TITULO_LIGERO = "SpaceGrotesk-Light"  # portada de los reels
PLANTILLA = RAIZ / "plantilla"
DIR_ICONOS = PLANTILLA / "iconos_linea"

NOMBRES = {1: "Gancho", 2: "Foto", 3: "Ícono", 4: "Dato", 5: "Cierre"}
# Tarjetas que llevan imagen de Krea, qué tipo y su caja (ancho, alto) en px.
TIPO_IMAGEN = {1: "icono", 2: "foto", 3: "linea"}
AREA_IMAGEN = {1: (660, 660), 2: (W, 620), 3: (260, 260)}
PROPORCION_KREA = {1: "1:1", 2: "16:9", 3: "1:1"}

PALETA_2026 = {"marino": "#12244A", "rojo": "#FF0006", "rojo2": "#FF1F35", "azul": "#005EFF",
               "gris": "#C9CACB", "gris_claro": "#E8E8E8", "blanco": "#FFFFFF", "negro": "#171719"}

RE_CIFRA = re.compile(r"[+\-]?(?:US\$|\$)?\d+(?:[.,]\d+)*\s?(?:%|x\b)?")


@lru_cache(maxsize=1)
def _registrar_fuentes() -> None:
    for nombre in (TITULO, TITULO_MEDIO, TITULO_LIGERO, TEXTO, TEXTO_SEMI):
        pdfmetrics.registerFont(TTFont(nombre, str(PLANTILLA / "fuentes" / f"{nombre}.ttf")))


def _colores() -> dict:
    p = {**PALETA_2026, **(marca().get("paleta_2026") or {})}
    return {k: HexColor(v) for k, v in p.items()}


@lru_cache(maxsize=1)
def iconos_linea() -> tuple[str, ...]:
    """Claves de los íconos de línea disponibles (nombre del archivo sin .svg)."""
    return tuple(sorted(p.stem for p in DIR_ICONOS.glob("*.svg")))


# ---------- texto ----------

def _envolver_voraz(palabras, fuente, tam, ancho):
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if stringWidth(prueba, fuente, tam) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def envolver(texto, fuente, tam, ancho):
    """Parte el texto en renglones de largo parejo (como `text-wrap: balance`): con el mismo número de renglones que
    cabe en `ancho`, busca el ancho más angosto posible, para que no queden renglones muy largos junto a otros muy
    cortos. Nunca parte palabras."""
    palabras = texto.split()
    lineas = _envolver_voraz(palabras, fuente, tam, ancho)
    if len(lineas) < 2:
        return lineas
    # Programación dinámica: entre todas las formas de repartir las palabras en esos n renglones (sin pasarse del
    # ancho), la de renglones más parejos (menor suma de cuadrados de la diferencia con el largo promedio).
    n, k = len(lineas), len(palabras)
    largo = {}

    def w(i, j):
        if (i, j) not in largo:
            largo[(i, j)] = stringWidth(" ".join(palabras[i:j]), fuente, tam)
        return largo[(i, j)]

    meta = w(0, k) / n
    INF = float("inf")
    costo = [[INF] * (k + 1) for _ in range(n + 1)]
    corte = [[0] * (k + 1) for _ in range(n + 1)]
    costo[0][0] = 0
    for r in range(1, n + 1):
        for j in range(r, k + 1):
            for i in range(r - 1, j):
                if costo[r - 1][i] == INF:
                    continue
                ancho_ij = w(i, j)
                if ancho_ij > ancho and j - i > 1:
                    continue
                c = costo[r - 1][i] + (ancho_ij - meta) ** 2
                if c < costo[r][j]:
                    costo[r][j], corte[r][j] = c, i
    if costo[n][k] == INF:
        return lineas
    resultado, j = [], k
    for r in range(n, 0, -1):
        i = corte[r][j]
        resultado.append(" ".join(palabras[i:j]))
        j = i
    return resultado[::-1]


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
    if alfa and (img.mode in ("RGBA", "LA", "P") or "transparency" in img.info):
        rgba = img.convert("RGBA")
        # Solo se trata como recorte transparente si de verdad tiene zonas transparentes; una foto PNG con canal alfa
        # pero opaca debe recortarse para llenar su espacio (si no, quedaba encajada con franjas).
        if rgba.getchannel("A").getextrema()[0] < 250:
            return rgba
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


def quitar_marco(img):
    """Recorta el marco de color uniforme que a veces trae la foto de Krea (márgenes claros alrededor de la imagen).
    Solo si las 4 esquinas son del mismo color y lo que queda dentro es claramente la foto."""
    from PIL import ImageChops
    rgb = img.convert("RGB")
    w, h = rgb.size
    esquinas = [rgb.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    if max(sum(abs(a - b) for a, b in zip(esquinas[0], c)) for c in esquinas[1:]) > 30:
        return img  # las esquinas son distintas: no hay marco
    fondo = rgb.copy()
    fondo.paste(tuple(round(sum(c[i] for c in esquinas) / 4) for i in range(3)), (0, 0, w, h))
    diferencia = ImageChops.difference(rgb, fondo).convert("L").point(lambda v: 255 if v > 28 else 0)
    caja = diferencia.getbbox()
    if not caja:
        return img
    x0, y0, x1, y1 = caja
    if (x1 - x0) * (y1 - y0) > 0.97 * w * h or (x1 - x0) < 0.4 * w or (y1 - y0) < 0.4 * h:
        return img  # casi sin marco, o lo detectado no parece la foto
    m = max(2, round(min(w, h) * 0.006))  # unos píxeles más adentro para no dejar línea del marco
    return img.crop((x0 + m, y0 + m, x1 - m, y1 - m))


def recortar(datos: bytes, ancho: float, alto: float, escala: float = 1.5, borde_suave: bool = False,
             foto: bool = False) -> bytes:
    """La imagen recortada (tipo «cover») a la proporción de la caja. borde_suave difumina apenas el contorno.
    foto=True quita antes el marco uniforme que a veces trae la foto, para que llene su espacio sin franjas."""
    from PIL import Image, ImageDraw, ImageFilter
    img = _abrir(datos, alfa=True)
    if foto and img.mode != "RGBA":
        img = quitar_marco(img)
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
        self.fondo_clave = "marino"

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


# ---------- rotación de colores ----------

# Cada pieza empieza con el color de su semana (1: azul marino, 2: azul, 3: gris, 4: rojo) y las tarjetas siguientes
# avanzan en ese mismo orden. El mes siguiente vuelve a empezar en azul marino.
ROTACION = ("marino", "azul", "gris", "rojo2")
# Por fondo: color del titular, del texto, de la cifra, de los trazos del ícono de línea y de su acento, de las comillas
# y versión de los logos.
TEMAS = {
    "marino": {"titulo": "gris", "texto": "blanco", "cifra": "blanco", "linea": "blanco", "acento": "rojo", "logos": "blanco"},
    "azul": {"titulo": "blanco", "texto": "blanco", "cifra": "blanco", "linea": "blanco", "acento": "marino", "logos": "blanco"},
    "gris": {"titulo": "marino", "texto": "marino", "cifra": "rojo", "linea": "marino", "acento": "rojo", "logos": "marino"},
    # Sobre marino y rojo, la cifra y el texto van en blanco (en beige no se leía bien con mucho texto).
    "rojo2": {"titulo": "blanco", "texto": "blanco", "cifra": "blanco", "linea": "blanco", "acento": "marino", "logos": "blanco"},
}


def inicio_de_semana(semana: int) -> int:
    return (max(1, int(semana or 1)) - 1) % len(ROTACION)


def color_de_tarjeta(numero: int, inicio: int = 0) -> str:
    """Clave del color de fondo de la tarjeta `numero` (1-5) en una pieza que empieza en `inicio`."""
    return ROTACION[(inicio + numero - 1) % len(ROTACION)]


def hex_de_tarjeta(numero: int, inicio: int = 0) -> str:
    return PALETA_2026[color_de_tarjeta(numero, inicio)]


def _fondo_con_imagen(L, datos):
    """Pinta el fondo de la tarjeta; si la imagen de Krea trae un fondo casi igual, usa ese tono exacto para que no se
    note el recuadro. Devuelve los bytes de la imagen o None si está dañada."""
    fondo = L.col[L.fondo_clave]
    if datos:
        try:
            if _abrir(datos, alfa=True).mode == "RGB":
                real = color_fondo_imagen(datos)
                if _parecido(real, PALETA_2026[L.fondo_clave]):
                    fondo = HexColor(real)
        except Exception:
            datos = None
    L.c.setFillColor(fondo)
    L.c.rect(0, 0, getattr(L, "ancho", W), getattr(L, "alto", H), stroke=0, fill=1)  # también sirve al reel
    return datos


def _svg_recoloreado(ruta, trazo, acento):
    """Ícono de línea de la guía (marino + rojo) con los colores que contrastan con el fondo de la tarjeta."""
    from reportlab.graphics.shapes import Group
    from svglib.svglib import svg2rlg
    dib = svg2rlg(str(ruta))

    def pintar(nodo):
        for hijo in getattr(nodo, "contents", []):
            pintar(hijo)
        for attr in ("strokeColor", "fillColor"):
            color = getattr(nodo, attr, None)
            if color is not None and hasattr(color, "red"):
                if color.red > 0.8 and color.green < 0.3 and color.blue < 0.3:  # el rojo del acento (cualquier tono)
                    setattr(nodo, attr, acento)
                elif color.red < 0.3 and color.blue < 0.5:                     # el azul marino de los trazos
                    setattr(nodo, attr, trazo)
    pintar(dib)
    return dib


# ---------- las 5 plantillas ----------

def t1_gancho(L, d):
    tema = TEMAS[L.fondo_clave]
    datos = _fondo_con_imagen(L, L.imagenes.get(1))
    ancho, alto = AREA_IMAGEN[1]
    x, y_sup = W - ancho - 50, H - alto - 50
    # Gancho como la portada del reel (Space Grotesk Light en mayúsculas), con la letra más grande que quepa en un área
    # invisible de 2/3 del ancho (desde la izquierda) por 1/2 del alto (desde arriba), centrado en ella. Las líneas
    # quedan alineadas a la izquierda entre sí.
    from rc.reels import GANCHO_INTER
    ax, ay, aw, ah = M, M, W * 2 / 3 - M, H / 2 - M
    secundario = (d.get("texto") or "").strip()
    alto_sec = 130 if secundario else 0
    titular = (d["titular"] or "").upper()
    if titular.strip():
        tam, lineas = ajustar(titular, TITULO_LIGERO, aw, ah - alto_sec, 240, GANCHO_INTER)
        ancho_txt = max(stringWidth(ln, TITULO_LIGERO, tam) for ln in lineas)
        alto_txt = len(lineas) * tam * GANCHO_INTER - tam * (GANCHO_INTER - 0.75)  # hasta la línea base
        x0 = ax + (aw - ancho_txt) / 2
        y0 = ay + (ah - alto_sec - alto_txt) / 2 - tam * 0.15
        L.bloque(titular, TITULO_LIGERO, tema["titulo"], x0, y0, ancho_txt + 1, ah, tam, inter=GANCHO_INTER)
        if secundario:
            L.bloque(secundario, TEXTO, tema["texto"], x0, y0 + alto_txt + tam * 0.4, aw, 120, 34)
    if datos:
        try:
            L.png(recortar(datos, ancho, alto, borde_suave=True), x, y_sup, ancho, alto)
            return
        except Exception:
            pass
    L.recuadro_guia(x + 60, y_sup + 60, ancho - 120, alto - 120, "ILUSTRACIÓN · Krea", d.get("nota", ""),
                    tinta=tema["texto"])


def t2_foto(L, d):
    tema = TEMAS[L.fondo_clave]
    L.fondo(L.fondo_clave)
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    ancho, alto = AREA_IMAGEN[2]
    L.bloque(texto, TEXTO, tema["texto"], M, 110, W - 2 * M - 40, H - alto - 180, 50, inter=1.3)
    datos = L.imagenes.get(2)
    if datos:
        try:
            L.png(recortar(datos, ancho, alto, foto=True), 0, H - alto, ancho, alto)
            L.c.saveState()
            L.c.setFillColor(L.col[L.fondo_clave])  # velo del color de la tarjeta
            L.c.setFillAlpha(0.45)
            L.c.rect(0, 0, ancho, alto, stroke=0, fill=1)
            L.c.restoreState()
            return
        except Exception:
            pass
    L.recuadro_guia(M, H - alto + 20, W - 2 * M, alto - 100, "FOTO · Krea (con velo del color de la tarjeta)",
                    d.get("nota", ""), tinta=tema["texto"])


def _icono_de(d: dict, alternativa: int) -> str:
    claves = iconos_linea()
    pedido = (d.get("icono") or "").strip().lower()
    return pedido if pedido in claves else claves[alternativa % len(claves)]


def t3_icono(L, d):
    tema = TEMAS[L.fondo_clave]
    # La imagen de Krea (ícono de línea generado) solo aplica a la tarjeta 3; la 4 sin cifra usa el ícono de la guía.
    datos = _fondo_con_imagen(L, L.imagenes.get(3) if L.tarjeta == 3 else None)
    ancho, alto = AREA_IMAGEN[3]
    puesto = False
    if datos:
        try:
            L.png(recortar(datos, ancho, alto, borde_suave=True), M - 40, 110, ancho, alto)
            puesto = True
        except Exception:
            pass
    if not puesto:
        dib = _svg_recoloreado(DIR_ICONOS / f"{_icono_de(d, d.get('alternativa', 0))}.svg",
                               L.col[tema["linea"]], L.col[tema["acento"]])
        k = 180 / dib.width
        dib.scale(k, k)
        renderPDF.draw(dib, L.c, M, H - 150 - dib.height * k)
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    L.bloque(texto, TEXTO, tema["texto"], M, 520, W - 2 * M - 60, H - 520 - M, 54, inter=1.3)


RE_RANGO = re.compile(r"\d+(?:[.,]\d+)*\s?[-–/]\s?\d+(?:[.,]\d+)*\s?%?")
RE_NUMERO = re.compile(r"(?:US\$|\$)?\d+(?:[.,]\d+)*")


def candidatos_cifra(texto: str) -> list[str]:
    """Cifras que se pueden resaltar en el texto, en orden de aparición y sin repetir: rangos («95-5»), números
    («95», «5») y números con su unidad («5%», «3x»). Ej.: «Regla 95-5: solo 5% compra» → 95-5, 95, 5, 5%."""
    texto = texto or ""
    hallados = []
    for m in RE_RANGO.finditer(texto):
        hallados.append((m.start(), 0, m.group(0).strip()))
    for m in RE_NUMERO.finditer(texto):
        hallados.append((m.start(), 1, m.group(0)))
        unidad = re.match(r"\s?(%|x\b)", texto[m.end():])
        if unidad:
            hallados.append((m.start(), 2, m.group(0) + unidad.group(0)))
    salida = []
    for _pos, _orden, c in sorted(hallados):
        if c not in salida:
            salida.append(c)
    return salida


# Palabras que convierten el número siguiente en un orden («Paso 1», «Etapa 2», «Regla #3»), no en una cifra de
# mercado: esos números no se muestran en grande.
RE_ORDEN = re.compile(r"(?:\b(?:paso|pasos|etapa|fase|step|nivel|punto|tip|consejo|clave|regla|n[°º.]?|no\.|número|numero)"
                      r"\s*#?\s*|#\s*)$", re.IGNORECASE)


def es_numero_de_orden(texto: str, m: re.Match) -> bool:
    """El número es un orden (paso, etapa…) o una lista («1.» / «1)» al inicio), sin unidad: no se resalta."""
    numero = m.group(0).strip()
    if not re.fullmatch(r"\d{1,2}", numero) or re.match(r"\s?[-–/]\s?\d", texto[m.end():]):
        return False  # con %, $, decimales o rango («95-5») es una cifra
    antes = texto[:m.start()]
    if RE_ORDEN.search(antes[-25:]):
        return True
    return not antes.strip() and re.match(r"\s*[.)]", texto[m.end():]) is not None


def separar_cifra(texto: str, preferida: str | None = None) -> tuple[str, str, str]:
    """(antes, cifra, después). Con `preferida` (una de candidatos_cifra) se resalta esa; si no, la primera cifra
    del texto. Cifra vacía si no hay."""
    texto = texto or ""
    if preferida:
        m = re.search(r"(?<![\d.,])" + re.escape(preferida) + (r"(?![\d%])" if preferida[-1].isdigit() else ""), texto)
        if m:
            return texto[:m.start()].strip(), m.group(0).strip(), texto[m.end():].strip()
    for m in RE_CIFRA.finditer(texto):
        if m.start() and texto[m.start() - 1].isdigit():
            continue  # «-5» dentro de «95-5»
        if re.search(r"\d", m.group(0)) and not es_numero_de_orden(texto, m):
            return texto[:m.start()].strip(), m.group(0).strip(), texto[m.end():].strip()
    return texto, "", ""


ALTO_MAYUS, ALTO_CIFRA = 0.70, 0.72  # alto de mayúsculas del texto y de los números de la cifra (fracción del cuerpo)


def t4_dato(L, d):
    tema = TEMAS[L.fondo_clave]
    todo = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    antes, cifra, despues = separar_cifra(todo, d.get("cifra"))
    L.fondo(L.fondo_clave)
    tam = 300
    while tam > 120 and stringWidth(cifra, TITULO, tam) > W - 2 * M:
        tam -= 10
    # Mismo aire visual arriba y abajo de la cifra: de la línea base del texto anterior al tope de la cifra, igual
    # que de la línea base de la cifra al tope de las mayúsculas del renglón siguiente.
    aire = 60 + 46 * (0.9 - ALTO_MAYUS)
    if (antes or "").strip():
        usado = L.bloque(antes, TEXTO, tema.get("texto_dato", tema["texto"]), M, 120, W - 2 * M - 60, 340, 46, inter=1.3)
        base_antes = 120 + usado - 46 * 1.3 + 46 * 0.9
        y = base_antes + aire - tam * (0.86 - ALTO_CIFRA)
    else:
        y = 120
    L.c.setFillColor(L.col[tema["cifra"]])
    L.c.setFont(TITULO, tam)
    L.c.drawString(M - tam * 0.04, H - y - tam * 0.86, cifra)
    y += tam * 0.86 + 60
    L.bloque(despues, TEXTO, tema.get("texto_dato", tema["texto"]), M, y, W - 2 * M - 60, H - y - M, 46, inter=1.3)


def t5_cierre(L, d):
    tema = TEMAS[L.fondo_clave]
    L.fondo(L.fondo_clave)
    L.c.setFillColor(L.col["marino" if L.fondo_clave == "rojo2" else "rojo"])
    L.c.setFont(TITULO, 520)
    L.c.drawString(W - M - 300, H - 520, "\u201d")
    texto = d.get("completo") or " ".join(p for p in (d["titular"], d["texto"]) if p)
    L.bloque(texto, TEXTO, tema["texto"], M, 330, 680, 560, 50, inter=1.3)
    oscuro = tema["logos"] == "marino"
    # Logo de Constellation en su propio renglón, ancho (2/3 del espacio útil) para que su trazo delgado se lea.
    ancho_c = (W - 2 * M) * 2 / 3
    alto_c = ancho_c * 52.35 / 369.25  # proporción del SVG
    y_c = H - M - alto_c
    L.svg(PLANTILLA / ("logo_constellation_negro.svg" if oscuro else "logo_constellation_blanco.svg"), M, y_c, ancho_c)
    L.png(PLANTILLA / ("logo_rc_marino_2026.png" if oscuro else "logo_rc_blanco_2026.png"), M, y_c - 50 - 80, 300, 80)


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
                guias: bool = False, imagenes: dict[int, bytes] | None = None, inicio: int = 0,
                cifras: dict | None = None) -> bytes:
    """guias=True dibuja los recuadros de imagen con su nota (vista previa); False los omite (descarga).

    inicio: color con que empieza la pieza (según su semana, ver ROTACION).
    variante + semilla solo cambian el ícono de línea cuando la tarjeta no pidió uno («Rehacer tarjetas»).
    """
    _registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = Lienzo(c, _colores(), guias=guias, imagenes=imagenes)
    for numero, (plantilla, datos) in enumerate(zip(plantillas_de(contenido), datos_tarjetas(contenido)), 1):
        L.tarjeta, L.fondo_clave = numero, color_de_tarjeta(numero, inicio)
        PLANTILLAS[plantilla](L, {**datos, "alternativa": variante + semilla * 3 + numero * 5,
                                  "cifra": (cifras or {}).get(str(numero))})
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
