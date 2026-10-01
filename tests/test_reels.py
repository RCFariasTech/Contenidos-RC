"""Guion visual de reels en PDF 9:16 (sin red)."""

import random
import unittest

import pymupdf  # solo para verificar el PDF en pruebas

from rc import reels

REEL = {
    "tema_especifico": "Marketing sensorial", "formato": "Reel",
    "escena_1_gancho": "¿Tu marca se huele?", "escena_2_desarrollo_a": "El olfato activa la memoria",
    "escena_3_desarrollo_b": "Diseñamos experiencias multisensoriales", "escena_4_desarrollo_c": "Medimos recordación real",
    "escena_5_cta": "Sígueme para más",
}


class TestReels(unittest.TestCase):
    def test_cinco_paginas_9_16_con_texto_editable(self):
        doc = pymupdf.open(stream=reels.generar_pdf(REEL), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1920))
        for pagina, campo in zip(doc, reels.CAMPOS):
            texto = " ".join(pagina.get_text().split())
            self.assertIn(REEL[campo], texto)
            self.assertIn("IMAGEN O VIDEO", texto)
        self.assertIn("ESCENA 1 · GANCHO · 0–5 s", " ".join(doc[0].get_text().split()))

    def test_el_texto_respeta_la_zona_segura_de_instagram(self):
        rnd = random.Random(3)
        lex = "activación retail experiencia consumidor marca estrategia conversión audiencia".split()
        for n in (1, 4, 8, 25):
            contenido = {c: " ".join(rnd.choice(lex) for _ in range(n)) for c in reels.CAMPOS}
            doc = pymupdf.open(stream=reels.generar_pdf(contenido, variante=n), filetype="pdf")
            for pagina in doc:
                for b in pagina.get_text("dict")["blocks"]:
                    for ln in b.get("lines", []):
                        x0, y0, x1, y1 = ln["bbox"]
                        self.assertGreaterEqual(y0, reels.ZONA_ARRIBA - 5)
                        self.assertLessEqual(y1, reels.H - reels.ZONA_ABAJO + 5)
                        self.assertTrue(20 <= x0 and x1 <= reels.W - 20)

    def test_nombre_de_archivo(self):
        self.assertEqual(reels.nombre_archivo(REEL, "2026-11-01"), "guion-visual-reel-2026-11-marketing-sensorial.pdf")


if __name__ == "__main__":
    unittest.main()
