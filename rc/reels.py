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
    def __init__(self, c, col, guias, imagenes=None, registro=None):
        self.c, self.col, self.guias, self.imagenes = c, col, guias, imagenes or {}
        # registro (lista): para el reel animado, los textos no se dibujan sino que se anotan con su posición, y
        # la pantalla los anima encima del fondo.
        self.registro = registro
        self.fondo_clave, self.tarjeta, self.ancho, self.alto = "marino", 0, W, H
        self.fotos = ()
        self.cifras = {}  # {"escena": cifra elegida para resaltar}

    def fondo(self, color):
        self.c.setFillColor(self.col[color])
        self.c.rect(0, 0, W, H, stroke=0, fill=1)

    def bloque(self, texto, fuente, color, x, y_sup, ancho, alto, tam_max, inter=1.15):
        if not (texto or "").strip():
            return 0
        tam, lineas = ajustar(texto, fuente, ancho, alto, tam_max, inter)
        y = H - y_sup - tam * 0.9
        for i, ln in enumerate(lineas):
            self.texto(ln, fuente, tam, color, x, y, linea=i)
            y -= tam * inter
        return len(lineas) * tam * inter

    def texto(self, ln, fuente, tam, color, x, y, linea=0, rol="texto"):
        """Una línea de texto (y = línea de base desde abajo), dibujada o anotada para animarla."""
        if self.registro is not None:
            self.registro.append({"texto": ln, "fuente": fuente, "tam": tam, "x": x, "y": H - y, "linea": linea,
                                  "color": "#" + self.col[color].hexval()[2:].upper(), "rol": rol})
            return
        self.c.setFillColor(self.col[color])
        self.c.setFont(fuente, tam)
        self.c.drawString(x, y, ln)

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
AREA_ICONO, AREA_LINEA = 520, 300
ALTO_FOTO = 1080
DOLLY = 0.12  # la foto del reel es 12 % más ancha que su espacio y se desliza de lado a lado  # escenas con foto: la foto ocupa el ancho completo desde arriba


def escenas_sin_cifra(contenido: dict) -> list[int]:
    """Escenas intermedias (2-4) cuyo texto no tiene cifra para mostrar en grande."""
    return [n for n in (2, 3, 4) if not tarjetas.separar_cifra((contenido.get(CAMPOS[n - 1]) or ""))[1]]


def fotos_validas(contenido: dict, fotos) -> list[int]:
    """Escenas con foto: solo entre las intermedias sin cifra, y solo si hay al menos dos (siempre queda un ícono)."""
    sin = escenas_sin_cifra(contenido)
    if len(sin) < 2:
        return []
    elegidas = [int(n) for n in (fotos or []) if int(n) in sin]
    return sorted(set(elegidas))[: len(sin) - 1]


def tipos_imagen(contenido: dict, fotos=()) -> dict[int, str]:
    """{escena: tipo} de las escenas que llevan imagen de Krea en este reel."""
    con_foto = fotos_validas(contenido, fotos)
    tipos = {1: "icono"}
    for n in escenas_sin_cifra(contenido):
        tipos[n] = "foto" if n in con_foto else "linea"
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


TAM_TXT_BASE, TAM_TXT_MAX, TAM_TXT_MIN, INTER_TXT = 72, 144, 40, 1.05
ALTO_MAYUS = 0.70  # alto de las mayúsculas de Space Grotesk, en proporción al tamaño


def _tam_texto_cifra(antes: str, despues: str, ancho: float, tam_cifra: float) -> float:
    """Tamaño del texto que acompaña a la cifra: con poco texto crece hasta el doble (144 pt) y se achica a medida que
    hay más, para que todo quepa centrado en la zona segura."""
    # Franja simétrica (mismo margen arriba y abajo que el inferior de Instagram) para que el grupo quede centrado.
    disponible = (H - 2 * ZONA_ABAJO) - tam_cifra * 0.86 - 40 - SEPARACION - 20
    tam = TAM_TXT_MAX
    while tam > TAM_TXT_MIN:
        alto = sum(len(tarjetas.envolver(t, TITULO, tam, ancho)) * tam * INTER_TXT for t in (antes, despues) if t.strip())
        if alto <= disponible and all(len(tarjetas.envolver(t, TITULO, tam, ancho)) <= 5 for t in (antes, despues)):
            return tam
        tam -= 4
    return TAM_TXT_MIN


def _tam_cifra(cifra):
    tam = 320
    while tam > 120 and stringWidth(cifra, TITULO, tam) > W - 2 * M:
        tam -= 10
    return tam


GANCHO_TAM, GANCHO_INTER, GANCHO_SEPARACION = 170, 0.98, 40


def _gancho(texto: str) -> str:
    return (texto or "").upper()


def _alto_gancho(texto: str, alto_max: float) -> float:
    if not (texto or "").strip():
        return 0
    tam, lineas = ajustar(_gancho(texto), tarjetas.TITULO_LIGERO, W - 2 * M, alto_max, GANCHO_TAM, GANCHO_INTER)
    return len(lineas) * tam * GANCHO_INTER


def caja_icono(contenido: dict) -> tuple[float, float, float]:
    """(x, y desde arriba, lado) del ícono isométrico de la portada (escena 1): alineado a la izquierda con el texto,
    encima de él. También sirve para superponer su video en la vista previa."""
    tarjetas._registrar_fuentes()
    lado = AREA_ICONO
    alto_texto = _alto_gancho(contenido.get(CAMPOS[0]) or "", ABAJO - ARRIBA - lado - GANCHO_SEPARACION - 30)
    # El ícono trae aire alrededor: se corre un poco a la izquierda para que el objeto quede alineado con el texto.
    # + margen por los trazos que bajan de la última línea (el interlineado es menor que 1).
    return M - lado * 0.06, _y_centrado(lado + GANCHO_SEPARACION + alto_texto + GANCHO_TAM * 0.15), lado


def _pagina(L, numero: int, texto: str, variante: int) -> None:
    cierre = numero == len(CAMPOS)  # la última escena lleva los logos y no lleva imagen
    fondo = "marino" if cierre else FONDOS[(variante + numero - 1) % len(FONDOS)][0]
    tema = tarjetas.TEMAS[fondo]
    L.fondo_clave, L.tarjeta = fondo, numero
    datos = None if cierre else tarjetas._fondo_con_imagen(L, L.imagenes.get(numero))
    if cierre:
        L.fondo(fondo)
        L.bloque(texto, TITULO, "blanco", M, 640, W - 2 * M, 1080 - 640, 96, inter=1.05)
        _logos(L)
        return
    ancho = W - 2 * M
    antes, cifra, despues = (tarjetas.separar_cifra(texto, L.cifras.get(str(numero))) if numero > 1
                             else (texto, "", ""))
    if cifra:  # cifra gigante entre dos líneas de texto, como la tarjeta de dato del carrusel; todo centrado
        tam = _tam_cifra(cifra)
        ancho_txt = ancho * 2 / 3  # el texto llega solo hasta 2 de 3 columnas y baja en más renglones
        tam_txt = _tam_texto_cifra(antes, despues, ancho_txt, tam)

        def alto(t):
            return len(tarjetas.envolver(t, TITULO, tam_txt, ancho_txt)) * tam_txt * INTER_TXT if t.strip() else 0
        h_antes, h_despues = alto(antes), alto(despues)
        total = h_antes + (40 if h_antes else 0) + tam * 0.86 + (SEPARACION + h_despues if h_despues else 0)
        # Centrado óptico: lo visible va desde la parte alta de las letras de la primera línea hasta la línea de base
        # de la última (las cajas de texto traen aire arriba que haría ver el grupo más abajo de lo que está).
        arriba_vis = (tam_txt * 0.9 - ALTO_MAYUS * tam_txt) if h_antes else (tam * 0.86 - ALTO_MAYUS * tam)
        if h_despues:
            abajo_vis = total - h_despues + (h_despues / (tam_txt * INTER_TXT) - 1) * tam_txt * INTER_TXT + tam_txt * 0.9
        else:
            abajo_vis = total  # termina en la línea de base de la cifra
        alto_vis = abajo_vis - arriba_vis
        y = max(ARRIBA, min((H - alto_vis) / 2 - arriba_vis, ABAJO - total))
        usado = L.bloque(antes, TITULO, tema["texto"], M, y, ancho_txt, h_antes + 2, tam_txt, inter=INTER_TXT)
        y += usado + (40 if usado else 0)
        L.texto(cifra, TITULO, tam, tema["cifra"], M - tam * 0.04, H - y - tam * 0.86, rol="cifra")
        y += tam * 0.86 + SEPARACION
        L.bloque(despues, TITULO, tema["texto"], M, y, ancho_txt, h_despues + 2, tam_txt, inter=INTER_TXT)
        return
    if numero in L.fotos:  # foto con velo del color de la escena arriba (como la tarjeta 2 del carrusel) y texto abajo
        alto_foto = ALTO_FOTO
        if datos:
            try:
                L.png(tarjetas.recortar(datos, W, alto_foto, foto=True), 0, 0, W, alto_foto)
                if L.registro is not None:  # reel animado: la foto se mueve (dolly lateral lento) bajo el velo
                    import base64
                    ancho_mov = round(W * (1 + DOLLY))
                    L.foto = {"src": "data:image/jpeg;base64," + base64.b64encode(
                                  tarjetas.recortar(datos, ancho_mov, alto_foto, escala=1, foto=True)).decode(),
                              "ancho": ancho_mov, "alto": alto_foto, "velo": L.col[fondo].hexval()[2:], "opacidad": 0.45}
                L.c.saveState()
                L.c.setFillColor(L.col[fondo])
                L.c.setFillAlpha(0.45)
                L.c.rect(0, H - alto_foto, W, alto_foto, stroke=0, fill=1)
                L.c.restoreState()
            except Exception:
                datos = None
        if not datos:
            L.guia(M, ARRIBA, W - 2 * M, alto_foto - ARRIBA - 40, "FOTO · Krea (con velo)", tema["texto"])
        arriba_texto = alto_foto + SEPARACION
        alto_texto = _alto_texto(texto, 96, ancho, ABAJO - arriba_texto)
        y_texto = arriba_texto + max(0, (ABAJO - arriba_texto - alto_texto) / 2)
        L.bloque(texto, TITULO, tema["texto"], M, y_texto, ancho, ABAJO - y_texto, 96, inter=1.05)
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
    if numero == 1:  # portada: Space Grotesk Light, en mayúsculas y grande
        y_texto = y_img + lado + GANCHO_SEPARACION
        # Mismo alto máximo que en caja_icono: así el tamaño de letra calculado para centrar es el que se dibuja.
        L.bloque(_gancho(texto), tarjetas.TITULO_LIGERO, tema["texto"], M, y_texto, ancho,
                 ABAJO - ARRIBA - lado - GANCHO_SEPARACION - 30, GANCHO_TAM, inter=GANCHO_INTER)
        return
    y_texto = y_img + lado + SEPARACION
    L.bloque(texto, TITULO, tema["texto"], M, y_texto, ancho, ABAJO - y_texto, 96, inter=1.05)


# En el logo de Constellation, la línea de base de la palabra CONSTELLATION está a esta fracción de su alto (desde
# arriba; el resto es «GLOBAL NETWORK», que no se usa para alinear).
LINEA_BASE_CONSTELLATION = 0.509


def _logos(L) -> None:
    """Cierre: logo RC / FARÍAS, «Miembros de» y, en su propio renglón, el logo de Constellation ancho (2/3 del espacio
    útil, desde el margen izquierdo) para que su trazo delgado se lea bien."""
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg
    dib = svg2rlg(str(tarjetas.PLANTILLA / "logo_constellation_blanco.svg"))
    ancho_logo = (W - 2 * M) * 2 / 3
    k = ancho_logo / dib.width
    dib.scale(k, k)
    alto_logo = dib.height * k
    abajo = ZONA_ABAJO + 4                         # borde inferior del logo de Constellation (desde abajo)
    renderPDF.draw(dib, L.c, M + 3, abajo)  # +3: la «C» del logo trae aire a la izquierda
    texto, tam = "Miembros de", 34
    base_texto = abajo + alto_logo + 30
    L.c.setFillColor(L.col["blanco"])
    L.c.setFont(TEXTO, tam)
    L.c.drawString(M, base_texto, texto)
    L.c.drawImage(str(tarjetas.PLANTILLA / "logo_rc_blanco_2026.png"), M - 2, base_texto + tam + 40, width=420,
                  height=128, mask="auto", preserveAspectRatio=True, anchor="sw")


def generar_pdf(contenido: dict, titulo: str = "Reel", variante: int = 0, semilla: int = 0,
                guias: bool = False, imagenes: dict[int, bytes] | None = None, fotos=(), cifras=None) -> bytes:
    """guias=True añade la etiqueta de cada escena (vista previa); False la omite (descarga)."""
    tarjetas._registrar_fuentes()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    c.setTitle(titulo)
    c.setAuthor("RC Farías")
    L = _Hoja(c, tarjetas._colores(), guias, imagenes)
    L.fotos = fotos_validas(contenido, fotos)
    L.cifras = cifras or {}
    for i, campo in enumerate(CAMPOS, 1):
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante + semilla)
        c.showPage()
    c.save()
    return buffer.getvalue()


PALABRAS_POR_SEGUNDO = 3
ENTRADA_S = 1.0     # lo que tarda en entrar el texto animado
MINIMO_S = 2.5
EXTRA_CIERRE_S = 1.0  # el cierre se queda un poco más para leer los logos


def duraciones(contenido: dict | None = None) -> list[float]:
    """Segundos de cada escena según su tiempo de lectura (~3 palabras por segundo) más la entrada del texto."""
    salida = []
    for i, campo in enumerate(CAMPOS):
        palabras = len(((contenido or {}).get(campo) or "").split())
        segundos = max(MINIMO_S, ENTRADA_S + palabras / PALABRAS_POR_SEGUNDO)
        if i == len(CAMPOS) - 1:
            segundos += EXTRA_CIERRE_S
        salida.append(round(segundos * 2) / 2)  # medios segundos
    return salida


def escenas_animables(contenido: dict, variante: int = 0, imagenes: dict[int, bytes] | None = None,
                      ancho: int = 1080, fotos=(), cifras=None) -> list[dict]:
    """Para armar el reel en video: cada escena como imagen de fondo SIN textos (JPEG en data URI) y los textos con
    su posición, fuente, tamaño y color (en px de 1080 x 1920; y = línea de base desde arriba), para que la pantalla
    los anime encima."""
    import base64
    import pymupdf
    tarjetas._registrar_fuentes()
    registros = [[] for _ in CAMPOS]
    fotos_mov = [None for _ in CAMPOS]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W, H))
    for i, campo in enumerate(CAMPOS, 1):
        L = _Hoja(c, tarjetas._colores(), False, imagenes, registro=registros[i - 1])
        L.fotos = fotos_validas(contenido, fotos)
        L.cifras = cifras or {}
        L.foto = None
        _pagina(L, i, (contenido.get(campo) or "").strip(), variante)
        fotos_mov[i - 1] = L.foto
        c.showPage()
    c.save()
    escenas = []
    with pymupdf.open(stream=buffer.getvalue(), filetype="pdf") as doc:
        for i, (pagina, segundos) in enumerate(zip(doc, duraciones(contenido))):
            jpg = pagina.get_pixmap(matrix=pymupdf.Matrix(ancho / W, ancho / W)).tobytes("jpg", jpg_quality=88)
            escenas.append({"fondo": "data:image/jpeg;base64," + base64.b64encode(jpg).decode(),
                            "duracion": segundos, "textos": registros[i], "foto": fotos_mov[i]})
    return escenas


def nombre_archivo(contenido: dict, mes_iso: str) -> str:
    return tarjetas.nombre_archivo(contenido, mes_iso).replace("tarjetas-", "guion-visual-reel-", 1)
