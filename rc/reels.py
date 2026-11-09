"""Guion visual de un reel en PDF vertical 9:16 (1080 x 1920) · sistema gráfico 2026: una página por escena.

Cada página trae el texto en pantalla (editable) y los tiempos. Escena 1: ícono isométrico de Krea (su versión
animada en video se descarga desde la app). Escenas 2-4: la primera cifra del texto en grande o, si no hay cifra, un
ícono de línea de Krea. Escena 5: cierre con logos, sin imagen.
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
    def __init__(self, c, col, guias, imagenes=None):
        self.c, self.col, self.guias, self.imagenes = c, col, guias, imagenes or {}
        self.fondo_clave, self.tarjeta, self.ancho, self.alto = "marino", 0, W, H

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

    def png(self, datos, x, y_sup, ancho, alto):
        from reportlab.lib.utils import ImageReader
        self.c.drawImage(ImageReader(io.BytesIO(datos)), x, H - y_sup - alto, ancho, alto, mask="auto",
                         preserveAspectRatio=True, anchor="sw")

    def guia(self, x, y_sup, ancho, alto, rotulo, tinta):
        """Recuadro punteado con el rótulo de qué va (solo en la vista previa)."""
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
        c.setFont(TITULO, 28)
        c.drawCentredString(x + ancho / 2, y + alto / 2 - 10, rotulo)


# Imagen de Krea por escena: 1 ícono isométrico (animado en video), 2-4 ícono de línea si la escena no tiene cifra;
# la 5 (cierre) no lleva imagen.
AREA_ICONO, AREA_LINEA = 860, 300


def tipos_imagen(contenido: dict) -> dict[int, str]:
    """{escena: tipo} de las escenas que llevan imagen de Krea en este reel."""
    tipos = {1: "icono"}
    for n in (2, 3, 4):
        if not tarjetas.separar_cifra((contenido.get(CAMPOS[n - 1]) or ""))[1]:
            tipos[n] = "linea"
    return tipos


ARRIBA, ABAJO = ZONA_ARRIBA, H - ZONA_ABAJO - 20  # zona segura: el contenido se centra verticalmente en ella
SEPARACION = 60


def _alto_texto(texto, tam_max, ancho, alto_max, inter=1.05):
    if not (texto or "").strip():
        return 0
    tam, lineas = ajustar(texto, TITULO, ancho, alto_max, tam_max, inter)
    return len(lineas) * tam * inter


def _y_centrado(total: float) -> float:
    """Borde superior para centrar un bloque de alto `total` en la página (mismo espacio arriba y abajo), sin salirse
    de la zona segura de Instagram."""
    return max(ARRIBA, min((H - total) / 2, ABAJO - total))


def _tam_cifra(cifra):
    tam = 320
    while tam > 120 and stringWidth(cifra, TITULO, tam) > W - 2 * M:
        tam -= 10
    return tam


def caja_icono(contenido: dict) -> tuple[float, float, float]:
    """(x, y desde arriba, lado) del ícono isométrico de la escena 1, para superponer su video en la vista previa."""
    lado = AREA_ICONO
    alto_texto = _alto_texto(contenido.get(CAMPOS[0]) or "", 96, W - 2 * M, ABAJO - ARRIBA - lado - SEPARACION)
    return (W - lado) / 2, _y_centrado(lado + SEPARACION + alto_texto), lado


def _pagina(L, numero: int, texto: str, variante: int) -> None:
    cierre = numero == len(CAMPOS)  # la última escena lleva los logos y no lleva imagen
    fondo = "marino" if cierre else FONDOS[(variante + numero - 1) % len(FONDOS)][0]
    tema = tarjetas.TEMAS[fondo]
    L.fondo_clave, L.tarjeta = fondo, numero
    datos = None if cierre else tarjetas._fondo_con_imagen(L, L.imagenes.get(numero))
    if cierre:
        L.fondo(fondo)
        L.bloque(texto, TITULO, "blanco", M, 700, W - 2 * M, 1180 - 700 - 20, 96, inter=1.05)
        _logos(L)
        return
    ancho = W - 2 * M
    antes, cifra, despues = tarjetas.separar_cifra(texto) if numero > 1 else (texto, "", "")
    if cifra:  # cifra gigante entre dos líneas de texto, como la tarjeta de dato del carrusel; todo centrado
        tam = _tam_cifra(cifra)
        h_antes = _alto_texto(antes, 72, ancho, 300)
        h_despues = _alto_texto(despues, 72, ancho, 400)
        total = h_antes + (40 if h_antes else 0) + tam * 0.86 + (SEPARACION + h_despues if h_despues else 0)
        y = _y_centrado(total)
        usado = L.bloque(antes, TITULO, tema["texto"], M, y, ancho, 300, 72, inter=1.05)
        y += usado + (40 if usado else 0)
        L.c.setFillColor(L.col[tema["cifra"]])
        L.c.setFont(TITULO, tam)
        L.c.drawString(M - tam * 0.04, H - y - tam * 0.86, cifra)
        y += tam * 0.86 + SEPARACION
        L.bloque(despues, TITULO, tema["texto"], M, y, ancho, ABAJO - y, 72, inter=1.05)
        return
    if numero == 1:
        x, y_img, lado = caja_icono({CAMPOS[0]: texto})
    else:
        lado = AREA_LINEA if datos else 200
        alto_texto = _alto_texto(texto, 96, ancho, ABAJO - ARRIBA - lado - SEPARACION)
        y_img = _y_centrado(lado + SEPARACION + alto_texto)
        x = M - 30 if datos else M
    puesto = False
    if datos:
        try:
            L.png(tarjetas.recortar(datos, lado, lado, borde_suave=True), x, y_img, lado, lado)
            puesto = True
        except Exception:
            pass
    if not puesto:
        if numero == 1:
            L.guia(x, y_img, lado, lado, "ÍCONO ISOMÉTRICO ANIMADO · Krea", tema["texto"])
        else:
            from reportlab.graphics import renderPDF
            dib = tarjetas._svg_recoloreado(
                tarjetas.DIR_ICONOS / f"{tarjetas._icono_de({}, variante + numero * 5)}.svg",
                L.col[tema["linea"]], L.col[tema["acento"]])
            k = 200 / dib.width
            dib.scale(k, k)
            renderPDF.draw(dib, L.c, x, H - y_img - dib.height * k)
    y_texto = y_img + lado + SEPARACION
    L.bloque(texto, TITULO, tema["titulo"] if numero == 1 else tema["texto"], M, y_texto, ancho,
             ABAJO - y_texto, 96, inter=1.05)


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
                guias: bool = False, imagenes: dict[int, bytes] | None = None) -> bytes:
    """guias=True añade la etiqueta de cada escena (vista previa); False la omite (descarga)."""
    tarjetas._registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = _Hoja(c, tarjetas._colores(), guias, imagenes)
    for i, campo in enumerate(CAMPOS, 1):
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante + semilla)
        c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    return tarjetas.nombre_archivo(contenido, mes_iso).replace("tarjetas-", "guion-visual-reel-", 1)
