"""Prompts de Krea para el sistema gráfico RC Farías 2026.

- Ícono isométrico (tarjeta 1): estilo del set de la guía visual, con los PNG
  publicados en /marca/iso/ como referencias de estilo.
- Ícono de línea (tarjeta 3): estilo de los íconos de línea de la guía, con /marca/linea/ como referencias.
- Foto (tarjeta 2 y reels): fotografía documental realista, gente común.
"""

MODELO = "google/nano-banana-pro"

REFERENCIAS_ICONO = ["/marca/iso/iso_2.png", "/marca/iso/iso_4.png",
                     "/marca/iso/iso_8.png", "/marca/iso/iso_9.png"]

ESTILO_ICONO = (
    "Create ONE new isometric 3D icon in exactly the same visual style as the "
    "reference images (RC Farías brand icon set). Subject (it may be described in Spanish): {tema}. "
    "STYLE: clean isometric 3/4 view from above, semi-flat 3D render, soft "
    "vector-like shading with smooth gradients, no textures, no realism. Strict "
    "palette: royal blue #005EFF and lighter blue gradients, bright red #FF0006 "
    "accents (arrows, chart lines, highlights, targets), white and light gray "
    "#E8E8E8 / #C9CACB surfaces, with subtle glossy translucent glass panels and "
    "gentle soft glow. Keep it simple: show ONLY the object(s) described in the "
    "subject (one object, or two interacting), with no extra props, scenery or "
    "decorative elements, like a clean floating editorial icon. No people unless "
    "the subject asks for them. No text, no "
    "letters, no numbers, no logos. Background: completely flat solid {fondo}, "
    "no floor, no shadows on the background, no frame, object centered with "
    "generous margin. The object must contrast clearly with the background."
)

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
    return ESTILO_ICONO.format(tema=tema.strip().rstrip("."), fondo=NOMBRES_COLOR.get(fondo, fondo))


def prompt_linea(tema: str, fondo: str = "gris", trazo: str = "marino", acento: str = "rojo") -> str:
    return ESTILO_LINEA.format(tema=tema.strip().rstrip("."), fondo=NOMBRES_COLOR.get(fondo, fondo),
                               trazo=NOMBRES_COLOR.get(trazo, trazo), acento=NOMBRES_COLOR.get(acento, acento))


def prompt_foto(escena: str) -> str:
    return ESTILO_FOTO.format(escena=escena.strip().rstrip("."))


def referencias_icono(base_url: str, tipo: str = "icono") -> list[str]:
    base = base_url.rstrip("/")
    return [base + r for r in (REFERENCIAS_LINEA if tipo == "linea" else REFERENCIAS_ICONO)]
