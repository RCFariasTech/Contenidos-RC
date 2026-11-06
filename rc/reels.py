"""Guion visual de un reel en PDF vertical 9:16 (1080 x 1920) · sistema gráfico 2026: una página por escena.

Cada página trae el texto en pantalla (editable), el espacio para la imagen o el video y los tiempos.
El diseñador lo abre en Adobe Express ("Empezar con tu contenido"), inserta los medios y anima.
Todo queda dentro de la zona segura de Instagram (sin texto en los ~220 px de arriba ni los ~450 px de abajo).
"""

import io

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from rc import tarjetas
from rc.tarjetas import M, TEXTO, TITULO, ajustar

W, H = 1080, 1920
ZONA_ARRIBA, ZONA_ABAJO = 220, 450
CAMPOS = ("escena_1_gancho", "escena_2_desarrollo_a", "escena_3_desarrollo_b",
          "escena_4_desarrollo_c", "escena_5_cta")
ROLES = (("Gancho", "0–5 s"), ("Desarrollo", "5–12 s"), ("Desarrollo", "12–20 s"),
         ("Desarrollo", "20–25 s"), ("CTA", "25–30 s"))
# (fondo, color del texto, color de apoyo) · paleta 2026. El cierre siempre es azul marino.
FONDOS = (("marino", "gris", "blanco"), ("azul", "blanco", "blanco"), ("gris", "marino", "marino"),
          ("rojo2", "blanco", "blanco"))


class _Hoja:
    def __init__(self, c, col, guias):
        self.c, self.col, self.guias = c, col, guias

    def fondo(self, color):
        self.c.setFillColor(self.col[color])
        self.c.rect(0, 0, W, H, stroke=0, fill=1)

    def bloque(self, texto, fuente, color, x, y_sup, ancho, alto, tam_max, inter=1.15):
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


def _pagina(L, numero: int, texto: str, variante: int) -> None:
    cierre = numero == len(CAMPOS)  # la última escena lleva los logos en vez de los nombres de las empresas
    fondo, c_texto, c_apoyo = ("marino", "blanco", "blanco") if cierre else FONDOS[(variante + numero - 1) % len(FONDOS)]
    rol, tiempo = ROLES[numero - 1]
    c = L.c
    L.fondo(fondo)
    if L.guias:  # la etiqueta con escena, rol y tiempo solo se ve en la vista previa
        L.bloque(f"ESCENA {numero} · {rol.upper()} · {tiempo}", TEXTO, c_apoyo, M, ZONA_ARRIBA + 20, W - 2 * M, 50, 30)
    # Espacio para la foto o el video (con velo azul, como la tarjeta 2 del carrusel)
    y_caja, alto_caja = ZONA_ARRIBA + 110, 520 if cierre else 800
    tinta = L.col["marino"] if fondo == "gris" else L.col["blanco"]
    c.saveState()
    c.setFillColor(tinta)
    c.setFillAlpha(0.12)
    c.setStrokeColor(tinta)
    c.setStrokeAlpha(0.7)
    c.setLineWidth(3)
    c.setDash(14, 10)
    c.roundRect(M, H - y_caja - alto_caja, W - 2 * M, alto_caja, 28, stroke=1, fill=1)
    c.restoreState()
    c.setFillColor(tinta)
    c.setFont(TITULO, 30)
    c.drawCentredString(W / 2, H - y_caja - alto_caja / 2 + 10, "FOTO O VIDEO · con velo azul")
    if L.guias:
        c.setFont(TEXTO, 24)
        c.drawCentredString(W / 2, H - y_caja - alto_caja / 2 - 28, f"Escena {numero} · {tiempo}")
    y_texto = y_caja + alto_caja + 60
    limite = 1180 if cierre else H - ZONA_ABAJO
    L.bloque(texto, TITULO, c_texto, M, y_texto, W - 2 * M, limite - y_texto - 20, 96, inter=1.05)
    if cierre:
        _logos(L)


# En el logo de Constellation, la línea de base de la palabra CONSTELLATION está a esta fracción de su alto (desde
# arriba; el resto es «GLOBAL NETWORK», que no se usa para alinear).
LINEA_BASE_CONSTELLATION = 0.509


def _logos(L) -> None:
    """Cierre: logo RC / FARÍAS blanco y, de pie de página, «Miembros de» + logo de Constellation blanco."""
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg
    L.c.drawImage(str(tarjetas.PLANTILLA / "logo_rc_blanco_2026.png"), M - 2, H - 1330, width=420, height=128,
                  mask="auto", preserveAspectRatio=True, anchor="sw")
    dib = svg2rlg(str(tarjetas.PLANTILLA / "logo_constellation_blanco.svg"))
    ancho_logo = 360
    k = ancho_logo / dib.width
    dib.scale(k, k)
    alto_logo = dib.height * k
    abajo = ZONA_ABAJO + 4
    texto, tam = "Miembros de", 34
    x0 = M  # sin compensar: la «M» de Sora ya cae en el margen; antes compensaba el espacio lateral de la «M» para que su borde visible caiga en el margen
    L.c.setFillColor(L.col["blanco"])
    L.c.setFont(TEXTO, tam)
    L.c.drawString(x0, abajo + alto_logo * (1 - LINEA_BASE_CONSTELLATION), texto)
    renderPDF.draw(dib, L.c, x0 + stringWidth(texto, TEXTO, tam) + 22, abajo)


def generar_pdf(contenido: dict, titulo: str = "Reel", variante: int = 0, semilla: int = 0,
                guias: bool = False) -> bytes:
    """guias=True añade la etiqueta de cada escena (vista previa); False la omite (descarga)."""
    tarjetas._registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = _Hoja(c, tarjetas._colores(), guias)
    for i, campo in enumerate(CAMPOS, 1):
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante + semilla)
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    return tarjetas.nombre_archivo(contenido, mes_iso).replace("tarjetas-", "guion-visual-reel-", 1)
