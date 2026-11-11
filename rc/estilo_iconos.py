"""Prompts de Krea para el sistema gráfico RC Farías 2026.

- Ilustración vectorial (tarjeta 1 y escena 1 del reel): estilo vectorial RC de la guía de Daniela
  (metáfora con protagonista, apoyos y un punto focal rojo), con sus referencias publicadas en Krea.
- Ícono de línea (tarjeta 3): estilo de los íconos de línea de la guía, con /marca/linea/ como referencias.
- Foto (tarjeta 2 y reels): fotografía documental realista, gente común.
"""

MODELO = "google/nano-banana-pro"

# Estilo vectorial RC (guía de Daniela, 10-nov-2026): referencias de estilo publicadas en Krea.
REF_FONDO_CLARO = "https://app-uploads.krea.ai/public/c011bd19-9c25-4ad2-b4b9-637a4152970b-image.png"
REF_FONDO_OSCURO = "https://app-uploads.krea.ai/public/f010ce21-afdf-4aeb-96aa-6e98dac256ac-image.png"
REF_MANOS = ["https://app-uploads.krea.ai/public/bd4d3ebe-4bd1-457b-a682-746e7187cb88-image.png",   # mano abierta
             "https://app-uploads.krea.ai/public/505cdc93-42b9-45f7-9b66-567803907fe2-image.png"]   # índice
REFERENCIAS_ICONO = [REF_FONDO_CLARO, REF_FONDO_OSCURO]

# Fondo de la tarjeta (paleta 2026, para que la ilustración se funda con ella) → bordes que separan del fondo.
FONDOS_VECTOR = {"marino": ("dark navy", "#12244A", "light"), "azul": ("royal blue", "#005EFF", "light"),
                 "gris": ("light grey", "#C9CACB", "dark"), "gris_claro": ("light grey", "#E8E8E8", "dark"),
                 "blanco": ("white", "#FFFFFF", "dark"), "rojo": ("red", "#FF0006", "light"),
                 "rojo2": ("red", "#FF1F35", "light")}

ESTILO_ICONO = (
    "Use the reference images ONLY as a style guide (flat 2D vector editorial illustration, simple geometric shapes, "
    "two-tone gradients, subtle risograph grain inside the illustrated elements, elegant composition). Do not copy "
    "their content. The brief may be written in Spanish.\n"
    "New illustration: {escena}.\n"
    "Protagonist: {protagonista}, with the richest color and volume through two-tone gradients and grain shading.\n"
    "Secondary: {apoyo}, simpler than the protagonist.\n"
    "Focal point: {focal} in {color_focal}, the only {nombre_focal} element.\n"
    "Colors: deep navy (#162447), electric blue (#1A5CFF), light grey (#E9E9E9, #CACBCC), charcoal (#353841, "
    "#171719), white. Depth from gradients, planes in slight perspective and translucent glass-like layers. "
    "Each gradient is one single continuous smooth seamless gradient, no visible bands or edges. "
    "Still-life composition: few large objects on a diagonal, generous negative space.\n"
    "People: abstract and faceless, no eyes, no mouth, no eyebrows, no eyelashes, no blush.\n"
    "Background: solid flat uniform {fondo_nombre} ({fondo_hex}), completely plain, no circle, no container, no "
    "gradient, no glow, no grain, no cast shadows. Edges in {bordes} colors to separate from the background.\n"
    "No decorative particles, no confetti, no scattered lines, dots, squares or arrows, no readable text, no logos, "
    "no outlines, no 3D render, no isometric technical diagram style, avoid small detailed parts."
)

_ETIQUETAS = {"escena": ("escena", "scene", "concepto"), "protagonista": ("protagonista", "protagonist"),
              "apoyo": ("apoyo", "secundarios", "secondary"), "focal": ("punto focal", "focal", "focal point")}


def partes_metafora(descripcion: str) -> dict:
    """Separa «Escena: … Protagonista: … Apoyo: … Punto focal: …». Si no viene estructurada, todo es la escena y el
    modelo decide protagonista, apoyos y punto focal."""
    import re
    texto = " ".join((descripcion or "").split()).strip(" .")
    etiquetas = sorted(((e, k) for k, es in _ETIQUETAS.items() for e in es), key=lambda x: -len(x[0]))
    patron = re.compile(r"(?i)\b(" + "|".join(re.escape(e) for e, _ in etiquetas) + r")\s*:")
    trozos = patron.split(texto)
    partes = {}
    if len(trozos) > 1:
        if trozos[0].strip(" .;"):
            partes["escena"] = trozos[0].strip(" .;")
        for i in range(1, len(trozos) - 1, 2):
            clave = next(k for e, k in etiquetas if e == trozos[i].lower())
            valor = trozos[i + 1].strip(" .;")
            if valor and clave not in partes:
                partes[clave] = valor
    else:
        partes["escena"] = texto
    partes.setdefault("escena", partes.get("protagonista", texto))
    partes.setdefault("protagonista", "the main element of the scene")
    partes.setdefault("apoyo", "two or three simple supporting elements that complete the metaphor")
    partes.setdefault("focal", "one key detail of the protagonist")
    return partes


REFERENCIAS_LINEA = ["/marca/linea/crecimiento.png", "/marca/linea/conexiones.png",
                     "/marca/linea/tiempo.png", "/marca/linea/procesos.png"]

ESTILO_LINEA = (
    "Create ONE new minimalist line icon in exactly the same style as the reference images (RC Farías brand line "
    "icon set). Subject (it may be described in Spanish): {tema}. STYLE: flat 2D outline icon made of a few simple geometric "
    "strokes, uniform medium stroke weight, square line ends, no fill, no shading, no gradients, no 3D. Strokes in "
    "{trazo} with ONE small accent stroke or detail in {acento}, like the references (which use navy strokes and a "
    "red accent). Very simple and readable at small size. No text, no letters, no numbers, no logos. Background: "
    "completely flat solid {fondo}, no shadows, no frame, icon centered with generous margin."
)

ESTILO_FOTO = (
    "Candid documentary photograph of a technology-driven brand event or "
    "activation in Colombia. {escena}. The scene clearly shows interactive "
    "technology (for example large LED screens, VR headsets, simulators, "
    "holograms, touch screens, multimedia games or phygital activations). "
    "Middle-class Latin "
    "American people, well-groomed and neatly dressed in clean, contemporary "
    "smart-casual clothes, tidy hair, light natural everyday makeup where it "
    "applies. Real people, not fashion models: natural skin texture with visible "
    "pores and subtle fine lines, unretouched. Clean, modern settings. Natural, "
    "soft available light. Anatomically correct hands with five fingers each, "
    "relaxed natural poses. Shot on 35mm, eye level, slightly imperfect framing, "
    "mild grain, no text overlays, no logos."
)


# Nombres de los colores de la paleta 2026 para los prompts.
NOMBRES_COLOR = {"marino": "dark navy #12244A", "azul": "royal blue #005EFF", "gris": "light gray #C9CACB",
                 "rojo": "bright red #FF0006", "rojo2": "bright red #FF1F35", "blanco": "white #FFFFFF"}


def prompt_icono(tema: str, fondo: str = "marino") -> str:
    """Ilustración vectorial RC (tarjeta 1 y escena 1 del reel) sobre el color de la tarjeta."""
    nombre, hexa, bordes = FONDOS_VECTOR.get(fondo, FONDOS_VECTOR["marino"])
    p = partes_metafora(tema)
    sobre_rojo = fondo.startswith("rojo")  # sobre fondo rojo el punto focal no se vería en rojo
    return ESTILO_ICONO.format(
        escena=p["escena"], protagonista=p["protagonista"], apoyo=p["apoyo"], focal=p["focal"],
        color_focal="white with a soft light grey gradient" if sobre_rojo else "a vivid red (#ED1D24) to coral (#EF3E40) gradient",
        nombre_focal="white" if sobre_rojo else "red",
        fondo_nombre=nombre, fondo_hex=hexa, bordes=bordes)


def prompt_linea(tema: str, fondo: str = "gris", trazo: str = "marino", acento: str = "rojo") -> str:
    return ESTILO_LINEA.format(tema=tema.strip().rstrip("."), fondo=NOMBRES_COLOR.get(fondo, fondo),
                               trazo=NOMBRES_COLOR.get(trazo, trazo), acento=NOMBRES_COLOR.get(acento, acento))


def prompt_foto(escena: str) -> str:
    return ESTILO_FOTO.format(escena=escena.strip().rstrip("."))


def referencias_icono(base_url: str, tipo: str = "icono", descripcion: str = "") -> list[str]:
    if tipo != "linea":
        manos = REF_MANOS if any(w in (descripcion or "").lower() for w in ("mano", "hand", "dedo", "índice")) else []
        return REFERENCIAS_ICONO + manos
    base = base_url.rstrip("/")
    return [base + r for r in REFERENCIAS_LINEA]
