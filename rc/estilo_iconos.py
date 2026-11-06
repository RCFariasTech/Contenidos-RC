"""Prompts de Krea para el sistema gráfico RC Farías 2026.

- Ícono isométrico (tarjeta 1): estilo del set de la guía visual, con los PNG
  publicados en /marca/iso/ como referencias de estilo.
- Foto (tarjeta 2 y reels): fotografía documental realista, gente común.
"""

MODELO = "google/nano-banana-pro"

REFERENCIAS_ICONO = ["/marca/iso/iso_2.png", "/marca/iso/iso_4.png",
                     "/marca/iso/iso_8.png", "/marca/iso/iso_9.png"]

ESTILO_ICONO = (
    "Create ONE new isometric 3D icon in exactly the same visual style as the "
    "reference images (RC Farías brand icon set). Subject: {tema}. "
    "STYLE: clean isometric 3/4 view from above, semi-flat 3D render, soft "
    "vector-like shading with smooth gradients, no textures, no realism. Strict "
    "palette: royal blue #005EFF and lighter blue gradients, bright red #FF0006 "
    "accents (arrows, chart lines, highlights, targets), white and light gray "
    "#E8E8E8 / #C9CACB surfaces, with subtle glossy translucent glass panels and "
    "gentle soft glow. Compose as a small cluster of 2-4 objects stacked or "
    "layered with slight overlap, like a floating editorial icon. Tiny simplified "
    "white/gray people figures only if needed, without faces. No text, no "
    "letters, no numbers, no logos. Background: completely flat solid navy "
    "#12244A, no floor, no shadows on the background, no frame, object centered "
    "with generous margin."
)

ESTILO_FOTO = (
    "Candid documentary photograph, Colombia. {escena}. Middle-class Latin "
    "American people, well-groomed and neatly dressed in clean, contemporary "
    "smart-casual clothes, tidy hair, light natural everyday makeup where it "
    "applies. Real people, not fashion models: natural skin texture with visible "
    "pores and subtle fine lines, unretouched. Clean, modern settings. Natural, "
    "soft available light. Anatomically correct hands with five fingers each, "
    "relaxed natural poses. Shot on 35mm, eye level, slightly imperfect framing, "
    "mild grain, no text overlays, no logos."
)


def prompt_icono(tema: str) -> str:
    return ESTILO_ICONO.format(tema=tema.strip().rstrip("."))


def prompt_foto(escena: str) -> str:
    return ESTILO_FOTO.format(escena=escena.strip().rstrip("."))


def referencias_icono(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    return [base + r for r in REFERENCIAS_ICONO]
