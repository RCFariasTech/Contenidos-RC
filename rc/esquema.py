"""JSON Schema de salida de una pieza (PLAN.md, sección 8.2)."""

INVESTIGACION = {
    "type": "object",
    "properties": {
        "tendencia": {"type": "string"},
        "resumen": {"type": "string"},
        "estrategia_clave": {"type": "string"},
        "fuente_titulo": {"type": "string"},
        "fuente_url": {"type": "string"},
        "fuente_fecha": {"type": "string"},
    },
    "required": ["tendencia", "resumen", "estrategia_clave",
                 "fuente_titulo", "fuente_url", "fuente_fecha"],
    "additionalProperties": False,
}

COMUNES = {
    "tema_especifico": {"type": "string"},
    "investigacion": INVESTIGACION,
    "caption": {"type": "string"},
    "cta": {"type": "string"},
    "hashtags": {"type": "array", "items": {"type": "string"}},
}

CAMPOS_TEXTO = {
    "Carrusel": ["slide_1_gancho", "slide_2", "slide_3", "slide_4", "slide_5_cierre"],
    "Reel": ["escena_1_gancho", "escena_2_desarrollo_a", "escena_3_desarrollo_b",
             "escena_4_desarrollo_c", "escena_5_cta"],
}


def _esquema_formato(formato: str) -> dict:
    campos = CAMPOS_TEXTO[formato]
    return {
        "type": "object",
        "properties": {
            **COMUNES,
            "formato": {"type": "string", "enum": [formato]},
            **{c: {"type": "string"} for c in campos},
        },
        "required": [*COMUNES, "formato", *campos],
        "additionalProperties": False,
    }


ESQUEMA_PIEZA = {f: _esquema_formato(f) for f in CAMPOS_TEXTO}
