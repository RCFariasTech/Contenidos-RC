"""Tarjetas de carrusel en PDF 3:4 (sin red)."""

import json
import unittest
from pathlib import Path

import pymupdf  # solo para verificar el PDF en pruebas

from rc import tarjetas
from tests.test_logica import carrusel

FIXTURE = Path(__file__).parent / "fixtures" / "mes_noviembre.json"


class TestTarjetas(unittest.TestCase):
    def test_pdf_de_cinco_paginas_3_4_con_texto_vivo(self):
        pieza = carrusel()
        doc = pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (1080, 1440))
        self.assertIn("Tu góndola ya es un medio", " ".join(doc[0].get_text().split()))
        self.assertIn("Constellation", doc[4].get_text())

    def test_contenido_viejo_sin_diseno(self):
        datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pieza = next(p["contenido"] for p in datos["piezas"] if p["formato"] == "Carrusel")
        self.assertNotIn("diseno", pieza)
        tarjs = tarjetas.datos_tarjetas(pieza)
        self.assertEqual(len(tarjs), 5)
        self.assertEqual(tarjs[0]["titular"], pieza["slide_1_gancho"])
        self.assertEqual(len(pymupdf.open(stream=tarjetas.generar_pdf(pieza), filetype="pdf")), 5)

    def test_estilos_varian_entre_carruseles(self):
        a, b = tarjetas.estilos_sugeridos(0), tarjetas.estilos_sugeridos(1)
        self.assertEqual((a[0], a[-1], b[0], b[-1]), (1, 7, 1, 7))
        self.assertNotEqual(a[1:4], b[1:4])

    def test_nombre_de_archivo(self):
        self.assertEqual(tarjetas.nombre_archivo({"tema_especifico": "Retail media: ¿ya?"}, "2026-11-01"),
                         "tarjetas-2026-11-retail-media-ya.pdf")


if __name__ == "__main__":
    unittest.main()
