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
        doc = pymupdf.open(stream=reels.generar_pdf(REEL, guias=True), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1920))
        for pagina, campo in zip(doc, reels.CAMPOS):
            texto = " ".join(pagina.get_text().split())
            self.assertIn(REEL[campo], texto)
            self.assertIn("IMAGEN O VIDEO", texto)
        self.assertIn("ESCENA 1 · GANCHO · 0–5 s", " ".join(doc[0].get_text().split()))

    def test_solo_el_cierre_lleva_logos_y_se_adaptan_al_fondo(self):
        for variante in range(5):
            doc = pymupdf.open(stream=reels.generar_pdf(REEL, variante=variante), filetype="pdf")
            self.assertTrue(all(not p.get_images() for p in list(doc)[:4]))   # RC / FARÍAS es una imagen PNG
            self.assertTrue(doc[4].get_images())
            self.assertGreater(len(doc[4].get_drawings()), 5)                   # Constellation es vector
            self.assertNotIn("Constellation", doc[4].get_text())                # logo, no texto
            texto = " ".join(doc[4].get_text().split())
            self.assertIn(REEL["escena_5_cta"], texto)
            self.assertIn("Miembros de", texto)
            # «Miembros de» comparte línea de base con CONSTELLATION y el logo llega al borde de la zona segura
            frase = doc[4].search_for("Miembros de")[0]
            logo = [d["rect"] for d in doc[4].get_drawings() if d["rect"].y0 > 1300 and d["rect"].x0 > frase.x1]
            self.assertTrue(logo)
            y0, y1 = min(r.y0 for r in logo), max(r.y1 for r in logo)
            linea_base = next(sp["origin"][1] for b in doc[4].get_text("dict")["blocks"] if b["type"] == 0
                              for ln in b["lines"] for sp in ln["spans"] if "Miembros" in sp["text"])
            self.assertAlmostEqual(linea_base, y0 + reels.LINEA_BASE_CONSTELLATION * (y1 - y0), delta=2.5)
            self.assertAlmostEqual(y1, reels.H - reels.ZONA_ABAJO, delta=6)       # pegado al límite inferior
            self.assertLessEqual(y1, reels.H - reels.ZONA_ABAJO)                    # sin pasarlo

    def test_la_descarga_no_trae_la_etiqueta_de_escena(self):
        descarga = pymupdf.open(stream=reels.generar_pdf(REEL), filetype="pdf")
        for pagina in descarga:
            texto = pagina.get_text()
            self.assertNotIn("ESCENA", texto)
            self.assertNotIn("0–5 s", texto)
        self.assertIn(REEL["escena_1_gancho"], " ".join(descarga[0].get_text().split()))

    def test_cada_escena_tiene_un_fondo_distinto(self):
        doc = pymupdf.open(stream=reels.generar_pdf(REEL, variante=2), filetype="pdf")
        fondos = [tuple(p.get_pixmap(matrix=pymupdf.Matrix(.1, .1)).pixel(2, 2)) for p in doc]
        self.assertEqual(len(set(fondos)), 5, fondos)
        otra = pymupdf.open(stream=reels.generar_pdf(REEL, variante=2, semilla=1), filetype="pdf")
        self.assertNotEqual(fondos[0], tuple(otra[0].get_pixmap(matrix=pymupdf.Matrix(.1, .1)).pixel(2, 2)))

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
